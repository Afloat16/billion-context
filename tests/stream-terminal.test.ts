import test from "node:test";
import assert from "node:assert/strict";
import { observeResponsesTerminalState } from "../src/stream-terminal.ts";

function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
    const enc = new TextEncoder();
    return new ReadableStream<Uint8Array>({
        start(controller) {
            for (const c of chunks) controller.enqueue(enc.encode(c));
            controller.close();
        },
    });
}

function sse(type: string, data: unknown): string {
    return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
}

test("SSE: response.completed terminal event → completed", async () => {
    const stream = sseStream([
        sse("response.created", { type: "response.created", response: { id: "r1" } }),
        sse("response.output_item.added", { type: "response.output_item.added", item: { type: "compaction" } }),
        sse("response.completed", { type: "response.completed", response: { id: "r1", status: "completed" } }),
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "completed");
});

test("SSE: response.failed → failed", async () => {
    const stream = sseStream([
        sse("response.created", { type: "response.created", response: { id: "r1" } }),
        sse("response.failed", { type: "response.failed", response: { status: "failed", error: { code: "boom" } } }),
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "failed");
});

test("SSE: response.incomplete → failed", async () => {
    const stream = sseStream([
        sse("response.incomplete", { type: "response.incomplete", response: { status: "incomplete" } }),
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "failed");
});

test("SSE: stream ends without terminal event (truncation) → unknown", async () => {
    const stream = sseStream([
        sse("response.created", { type: "response.created", response: { id: "r1" } }),
        sse("response.output_item.added", { type: "response.output_item.added", item: { type: "message" } }),
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "unknown");
});

test("SSE: empty stream → unknown", async () => {
    assert.equal(await observeResponsesTerminalState(sseStream([]), true), "unknown");
});

test("SSE: data-line type fallback when event: lines are stripped", async () => {
    const stream = sseStream([
        `data: ${JSON.stringify({ type: "response.created", response: { id: "r1" } })}\n\n`,
        `data: ${JSON.stringify({ type: "response.completed", response: { id: "r1" } })}\n\n`,
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "completed");
    const failed = sseStream([`data: ${JSON.stringify({ type: "response.failed", response: {} })}\n\n`]);
    assert.equal(await observeResponsesTerminalState(failed, true), "failed");
});

test("SSE: CRLF endings and events split across chunks", async () => {
    const full = sse("response.created", { type: "response.created" }) + sse("response.completed", { type: "response.completed" });
    const crlf = full.replace(/\n/g, "\r\n");
    const mid = Math.floor(crlf.length / 2);
    assert.equal(await observeResponsesTerminalState(sseStream([crlf.slice(0, mid), crlf.slice(mid)]), true), "completed");
});

test("SSE: terminal event wins even if more events follow", async () => {
    const stream = sseStream([
        sse("response.completed", { type: "response.completed", response: { id: "r1" } }),
        sse("response.output_item.added", { type: "response.output_item.added", item: {} }),
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "completed");
});

test("SSE: non-JSON data lines are ignored, not fatal", async () => {
    const stream = sseStream([
        "data: [DONE]\n\n",
        sse("response.completed", { type: "response.completed", response: { id: "r1" } }),
    ]);
    assert.equal(await observeResponsesTerminalState(stream, true), "completed");
});

for (const fragment of [
    "event: response.completed\n",
    'event: response.completed\ndata: {"type":"response.completed",',
    'event: response.completed\ndata: {"type":"response.completed"}\n',
    "event: response.completed\n\n",
    "event: response.completed\ndata: not-json\n\n",
]) {
    test(`SSE: incomplete or unusable terminal frame cannot authorize rebase: ${JSON.stringify(fragment)}`, async () => {
        assert.equal(await observeResponsesTerminalState(sseStream([fragment]), true), "unknown");
    });
}

test("SSE: terminal state waits for the frame delimiter", async () => {
    const encoder = new TextEncoder();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({ start(c) { controller = c; } });
    let settled = false;
    const observed = observeResponsesTerminalState(stream, true).then((state) => { settled = true; return state; });
    controller.enqueue(encoder.encode('event: response.completed\ndata: {"type":"response.completed"}\n'));
    await new Promise<void>((resolve) => setImmediate(resolve));
    const premature = settled;
    if (!premature) controller.enqueue(encoder.encode("\n"));
    assert.equal(await observed, "completed");
    assert.equal(premature, false, "a parsed terminal data line alone is not a dispatched event");
});

test("SSE: joins multiline data before reading the terminal type", async () => {
    const frame = 'data: {\ndata: "type": "response.completed",\ndata: "response": {"status":"completed"}}\n\n';
    assert.equal(await observeResponsesTerminalState(sseStream([frame]), true), "completed");
});

test("SSE: lone CR endings, including the final delimiter, complete the frame", async () => {
    const frame = sse("response.completed", { type: "response.completed" }).replace(/\n/g, "\r");
    assert.equal(await observeResponsesTerminalState(sseStream([...frame]), true), "completed");
});

test("SSE: split CRLF inside multiline data never dispatches a partial frame", async () => {
    const frame = 'event: response.completed\r\ndata: {"type":\r\ndata: "response.completed"}\r\n\r\n';
    assert.equal(await observeResponsesTerminalState(sseStream([...frame]), true), "completed");
});

test("SSE: later event fields replace earlier labels in the same frame", async () => {
    const frame = 'event: response.completed\nevent: response.failed\ndata: {"type":"response.failed"}\n\n';
    assert.equal(await observeResponsesTerminalState(sseStream([frame]), true), "failed");
});

test("SSE: a failure event label cannot be overridden by a conflicting success payload", async () => {
    assert.equal(await observeResponsesTerminalState(sseStream([
        sse("response.failed", { type: "response.completed" }),
    ]), true), "failed");
});

test("JSON: output array present → completed", async () => {
    const stream = sseStream([JSON.stringify({ id: "r1", status: "completed", output: [{ type: "compaction", encrypted_content: "x" }], usage: {} })]);
    assert.equal(await observeResponsesTerminalState(stream, false), "completed");
});

test("JSON: error field present → failed", async () => {
    const stream = sseStream([JSON.stringify({ error: { message: "compact failed" } })]);
    assert.equal(await observeResponsesTerminalState(stream, false), "failed");
});

test("JSON: unparseable body → unknown", async () => {
    assert.equal(await observeResponsesTerminalState(sseStream(["<html>502 bad gateway</html>"]), false), "unknown");
});

test("JSON: non-object body → unknown", async () => {
    assert.equal(await observeResponsesTerminalState(sseStream(["42"]), false), "unknown");
});

test("JSON: empty body → unknown", async () => {
    assert.equal(await observeResponsesTerminalState(sseStream([]), false), "unknown");
});

test("JSON: body without output field → unknown", async () => {
    assert.equal(await observeResponsesTerminalState(sseStream([JSON.stringify({ id: "r1", status: "completed" })]), false), "unknown");
});

test("JSON: oversized body → unknown (safe default)", async () => {
    const big = JSON.stringify({ output: ["x".repeat((16 << 20) + 1)] });
    assert.equal(await observeResponsesTerminalState(sseStream([big]), false), "unknown");
});
