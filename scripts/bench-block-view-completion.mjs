// Manual production-planner benchmark; no wall-clock threshold in CI.
// node --expose-gc --import tsx scripts/bench-block-view-completion.mjs 5000
import { createHash } from "node:crypto";
import { performance } from "node:perf_hooks";
import { planIngest } from "../src/storage/ingest.ts";

const count = Number(process.argv[2] ?? 5000);
if (!Number.isSafeInteger(count) || count <= 0) throw new Error("block count must be a positive safe integer");
const blocks = Array.from({ length: count }, (_, i) => ({
    blockId: `b${i + 1}`, runId: `r${i + 1}`, tier: 1, summary: `summary ${i}`,
    directMessageIds: [], effectiveMessageIds: [], directBlockIds: [],
    compressedTokens: 10, createdAt: 1_000 + i, survivedCount: 0, generation: "young", active: true,
}));
for (const sparse of [false, true]) {
    const session = {
        id: "bench", createdAt: 1_000, lastSeen: 2_000, meta: {}, stats: {}, metadata: {},
        state: { blocks, nextBlockId: count + 1, nextRunId: count + 1, messageRefs: { byRaw: {}, byRef: {} } },
        blockContents: new Map(blocks.filter((_, i) => !sparse || i % 2 === 0).map((b) => [b.blockId, { one: null, full: { text: `original ${b.blockId}`, count: 1 } }])),
    };
    planIngest(session);
    const timings = [];
    let digest;
    for (let i = 0; i < 3; i++) {
        global.gc?.();
        const start = performance.now();
        const plan = planIngest(session);
        timings.push(performance.now() - start);
        const current = createHash("sha256").update(JSON.stringify(plan)).digest("hex");
        if (digest !== undefined && digest !== current) throw new Error("planner output changed across repeats");
        digest = current;
    }
    console.log(JSON.stringify({ blocks: count, sparse, runsMs: timings, medianMs: [...timings].sort((a, b) => a - b)[1], digest }));
}
