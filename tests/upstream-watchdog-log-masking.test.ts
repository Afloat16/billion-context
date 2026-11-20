import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { type TestContext } from "node:test";
import { withFetchTransport } from "../src/fetch-transport.ts";
import { _liveUpstreamTimersForTest, _resetFetchUtilForTest, fetchWithTimeout } from "../src/fetch-util.ts";
import { closeLogger, configureLogger } from "../src/logger.ts";
import { isMaskHostsEnabled, setMaskHostsEnabled } from "../src/log-mask.ts";

function logFixture(t: TestContext, maskHosts = true) {
    const root = mkdtempSync(join(tmpdir(), "watchdog-log-mask-"));
    const file = join(root, "bili.log");
    const previous = isMaskHostsEnabled();
    setMaskHostsEnabled(maskHosts);
    configureLogger(file);
    t.mock.timers.enable({ apis: ["setTimeout"] });
    t.after(async () => {
        t.mock.timers.reset();
        await closeLogger();
        configureLogger("off");
        _resetFetchUtilForTest();
        setMaskHostsEnabled(previous);
        rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 30 });
    });
    return async () => {
        await closeLogger();
        return readFileSync(file, "utf8").split("\n").filter((line) => line.includes("upstream watchdog fired"));
    };
}

const targets = [
    { name: "private relay", host: "company-relay.internal:8443", mask: true, expected: "<private-host>:8443" },
    { name: "public API", host: "api.openai.com", mask: true, expected: "api.openai.com" },
    { name: "local host-visibility opt-out", host: "company-relay.internal:8443", mask: false, expected: "company-relay.internal:8443" },
];

for (const phase of ["first-byte", "body"] as const) {
    for (const target of targets) {
        test(`${phase} watchdog applies URL privacy to its written ${target.name} log`, async (t) => {
            const lines = logFixture(t, target.mask);
            const url = `https://alice:short-pass@${target.host}/v1/messages?custom-secret=unrecognizable-value#private-fragment`;
            if (phase === "first-byte") {
                const pending = withFetchTransport((_url, options) => new Promise<Response>((_resolve, reject) => {
                    assert.ok(options.signal);
                    options.signal.addEventListener("abort", () => reject(options.signal?.reason), { once: true });
                }), () => fetchWithTimeout(url, { method: "POST", body: "{}" }, 1000));
                const rejected = assert.rejects(pending, { name: "AbortError" });
                t.mock.timers.tick(1000);
                await rejected;
            } else {
                const { response, clearTimer } = await withFetchTransport(async (_url, options) => {
                    assert.ok(options.signal);
                    const signal = options.signal;
                    return new Response(new ReadableStream<Uint8Array>({
                        start(controller) {
                            controller.enqueue(new TextEncoder().encode("first chunk"));
                            signal.addEventListener("abort", () => controller.error(signal.reason), { once: true });
                        },
                    }));
                }, () => fetchWithTimeout(url, { method: "POST", body: "{}" }, 1000));
                const reader = response.body!.getReader();
                try {
                    assert.equal(new TextDecoder().decode((await reader.read()).value), "first chunk");
                    const rejected = assert.rejects(reader.read(), { name: "AbortError" });
                    t.mock.timers.tick(1000);
                    await rejected;
                } finally {
                    clearTimer();
                    reader.releaseLock();
                }
            }
            assert.equal(_liveUpstreamTimersForTest(), 0);
            const written = await lines();
            assert.equal(written.length, 1);
            assert.ok(written[0]!.includes(`(${phase} phase, 1000ms budget)`));
            assert.ok(written[0]!.includes(`POST https://${target.expected}/v1/messages aborted:`), written[0]);
            assert.doesNotMatch(written[0]!, /alice|short-pass|custom-secret|unrecognizable-value|private-fragment/);
        });
    }
}

test("a consumed successful response emits no watchdog warning", async (t) => {
    const lines = logFixture(t);
    const { response, clearTimer } = await withFetchTransport(async () => new Response("complete"), () =>
        fetchWithTimeout("https://company-relay.internal/v1/messages", {}, 1000));
    try { assert.equal(await response.text(), "complete"); } finally { clearTimer(); }
    t.mock.timers.tick(10000);
    assert.equal(_liveUpstreamTimersForTest(), 0);
    assert.deepEqual(await lines(), []);
});

test("client cancellation emits no upstream watchdog warning", async (t) => {
    const lines = logFixture(t);
    const client = new AbortController();
    const pending = withFetchTransport((_url, options) => new Promise<Response>((_resolve, reject) => {
        assert.ok(options.signal);
        options.signal.addEventListener("abort", () => reject(options.signal?.reason), { once: true });
    }), () => fetchWithTimeout("https://company-relay.internal/v1/messages", {}, 1000, client.signal));
    const rejected = assert.rejects(pending, { name: "AbortError" });
    client.abort();
    await rejected;
    t.mock.timers.tick(10000);
    assert.equal(_liveUpstreamTimersForTest(), 0);
    assert.deepEqual(await lines(), []);
});
