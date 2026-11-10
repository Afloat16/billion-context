// #321 PR-C: terminal-state observer for native-compaction responses. The
// rebase marker may only fire on "completed": a failed/incomplete/truncated
// stream means the client kept its history, and rebasing on a compaction that
// never happened discards valid blocks (#249). "unknown" is the safe default
// (no rebase; the next request self-heals via kernel message-id deactivation).

import { finalizeSseLineEndings, normalizeSseLineEndings } from "./sse-util.js";

type TerminalState = "completed" | "failed" | "unknown";

const SUCCEEDED = "response.completed";
const FAILED_EVENTS = new Set(["response.failed", "response.incomplete"]);
const MAX_JSON_BYTES = 16 << 20;

export async function observeResponsesTerminalState(stream: ReadableStream<Uint8Array>, isStream: boolean): Promise<TerminalState> {
    return isStream ? observeSseTerminalState(stream) : observeJsonTerminalState(stream);
}

function terminalFromSseEvent(frame: string): TerminalState | null {
    let event = "";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
        const colon = line.indexOf(":");
        const field = colon < 0 ? line : line.slice(0, colon);
        const raw = colon < 0 ? "" : line.slice(colon + 1);
        const value = raw.startsWith(" ") ? raw.slice(1) : raw;
        if (field === "event") event = value;
        else if (field === "data") data.push(value);
    }
    if (data.length === 0) return null;
    try {
        const payload: unknown = JSON.parse(data.join("\n"));
        if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return null;
        const type = (payload as { type?: unknown }).type;
        if (FAILED_EVENTS.has(event) || (typeof type === "string" && FAILED_EVENTS.has(type))) return "failed";
        const name = typeof type === "string" ? type : event;
        if (name === SUCCEEDED) return "completed";
    } catch {
        // An event label without usable JSON is not evidence that compaction
        // completed at the client. Preserve the existing history instead.
    }
    return null;
}

async function observeSseTerminalState(stream: ReadableStream<Uint8Array>): Promise<TerminalState> {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let state: TerminalState = "unknown";
    try {
        for (;;) {
            const { done, value } = await reader.read();
            buf += done ? decoder.decode() : decoder.decode(value, { stream: true });
            buf = done ? finalizeSseLineEndings(buf) : normalizeSseLineEndings(buf);
            let end: number;
            while ((end = buf.indexOf("\n\n")) >= 0) {
                const frame = buf.slice(0, end);
                buf = buf.slice(end + 2);
                const next = terminalFromSseEvent(frame);
                if (next !== null) {
                    state = next;
                    break;
                }
            }
            if (state !== "unknown") {
                // Release this tee branch; the client branch keeps draining the source.
                await reader.cancel().catch(() => {});
                break;
            }
            // EOF is not an event delimiter: a partial completion frame must
            // never authorize rebasing the client's still-uncompacted history.
            if (done) break;
        }
    } catch {
        return "unknown";
    } finally {
        reader.releaseLock();
    }
    return state;
}

async function observeJsonTerminalState(stream: ReadableStream<Uint8Array>): Promise<TerminalState> {
    const reader = stream.getReader();
    const chunks: Buffer[] = [];
    let size = 0;
    let overflow = false;
    try {
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            if (!overflow) {
                size += value.length;
                if (size <= MAX_JSON_BYTES) {
                    chunks.push(Buffer.from(value));
                } else {
                    overflow = true;
                }
            }
        }
    } catch {
        return "unknown";
    } finally {
        reader.releaseLock();
    }
    if (overflow) return "unknown";
    const text = Buffer.concat(chunks).toString("utf8").trim();
    if (!text) return "unknown";
    let body: unknown;
    try {
        body = JSON.parse(text);
    } catch {
        return "unknown";
    }
    if (typeof body !== "object" || body === null) return "unknown";
    const rec = body as Record<string, unknown>;
    if (rec.error !== undefined) return "failed";
    if (Array.isArray(rec.output)) return "completed";
    return "unknown";
}
