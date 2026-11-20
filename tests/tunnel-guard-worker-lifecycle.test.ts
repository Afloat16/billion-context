import assert from "node:assert/strict";
import { syncBuiltinESMExports } from "node:module";
import test, { type TestContext } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import workerThreads, { Worker, type WorkerOptions } from "node:worker_threads";
import { workerResolveHost } from "../src/tunnel-guard.ts";

function observeWorker(t: TestContext, prelude = "") {
    const workers: Array<{ worker: Worker; exited: Promise<number> }> = [];
    class ObservedWorker extends Worker {
        constructor(source: string | URL, options?: WorkerOptions) {
            assert.ok(typeof source === "string" && options?.eval);
            super(`${prelude}\n${source}`, { ...options, execArgv: [] });
            workers.push({ worker: this, exited: new Promise((resolve) => this.once("exit", resolve)) });
        }
    }
    const replacement = t.mock.method(workerThreads, "Worker", ObservedWorker);
    syncBuiltinESMExports();
    t.after(async () => {
        replacement.mock.restore();
        syncBuiltinESMExports();
        await Promise.all(workers.map(({ worker }) => worker.terminate()));
    });
    return async () => {
        assert.equal(workers.length, 1);
        const { worker, exited } = workers[0]!;
        const outcome = await Promise.race([
            exited.then((code) => ({ code })),
            delay(1000, undefined, { ref: false }).then(() => ({ code: null })),
        ]);
        assert.notEqual(outcome.code, null, "the completed one-shot probe must not retain a live worker");
        assert.equal(worker.threadId, -1);
        return outcome.code;
    };
}

test("the inner DNS timeout stops its one-shot worker", async (t) => {
    const exited = observeWorker(t, `
        require("node:dns").promises.lookup = () => {
            setInterval(() => {}, 10000);
            return new Promise(() => {});
        };
    `);
    await assert.rejects(workerResolveHost("stalled-lookup.invalid"), (error: unknown) => {
        assert.ok(error instanceof Error);
        assert.equal((error as NodeJS.ErrnoException).code, "ETIMEDOUT");
        assert.match(error.message, /worker dns lookup failed/);
        return true;
    });
    assert.equal(await exited(), 1);
});

test("the outer deadline still stops a worker that cannot send its inner verdict", async (t) => {
    const exited = observeWorker(t, "Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0);");
    await assert.rejects(workerResolveHost("localhost"), { code: "ETIMEDOUT", message: "ETIMEDOUT" });
    assert.equal(await exited(), 1);
});

test("a successful native lookup exits normally and keeps its addresses", async (t) => {
    const exited = observeWorker(t);
    const addresses = await workerResolveHost("localhost");
    assert.ok(addresses.includes("127.0.0.1") || addresses.includes("::1"));
    assert.equal(await exited(), 0);
});
