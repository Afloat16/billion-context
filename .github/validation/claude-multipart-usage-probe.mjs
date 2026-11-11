import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { query } from '@anthropic-ai/claude-agent-sdk';

const root = await mkdtemp(join(tmpdir(), 'claude-usage-protocol-'));
const config = join(root, 'config');
const cwd = join(root, 'work');
await mkdir(config);
await mkdir(cwd);
const startUsage = { input_tokens: 11, cache_creation_input_tokens: 23, cache_read_input_tokens: 101, output_tokens: 1 };
const requests = [];
const wire = [];
const server = createServer(async (req, res) => {
  let text = '';
  for await (const chunk of req) text += chunk;
  const body = text ? JSON.parse(text) : {};
  requests.push({ path: req.url, method: req.method, model: body.model, streaming: body.stream, tools: body.tools?.length ?? 0 });
  if (requests.length > 8) {
    res.writeHead(429, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ type: 'error', error: { type: 'rate_limit_error', message: 'owned fixture request budget' } }));
    return;
  }
  if (req.url?.includes('/messages/count_tokens')) {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ input_tokens: 135 }));
    return;
  }
  if (!req.url?.startsWith('/v1/messages') || req.method !== 'POST') {
    res.writeHead(404, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ type: 'error', error: { type: 'not_found_error', message: 'owned fixture endpoint' } }));
    return;
  }
  assert.equal(body.stream, true, 'exercise the native SSE parser');
  assert.equal(body.tools?.length ?? 0, 0, 'no tool surface');
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
  const emit = event => { wire.push(event); res.write('event: ' + event.type + '\ndata: ' + JSON.stringify(event) + '\n\n'); };
  emit({ type: 'message_start', message: { id: 'msg_owned_multipart_usage', type: 'message', role: 'assistant',
    model: body.model, content: [], stop_reason: null, stop_sequence: null, usage: startUsage } });
  for (const [index, text] of ['first independent block', 'second independent block'].entries()) {
    emit({ type: 'content_block_start', index, content_block: { type: 'text', text: '' } });
    emit({ type: 'content_block_delta', index, delta: { type: 'text_delta', text } });
    emit({ type: 'content_block_stop', index });
  }
  emit({ type: 'message_delta', delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: 17 } });
  emit({ type: 'message_stop' });
  res.end();
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const baseURL = 'http://127.0.0.1:' + server.address().port;
const abortController = new AbortController();
const timer = setTimeout(() => abortController.abort(), 90_000);
const frames = [];
let stderr = '';
try {
  for await (const frame of query({
    prompt: 'Return the two controlled text blocks.',
    options: {
      cwd, model: 'claude-sonnet-4-6', maxTurns: 1,
      tools: [], allowedTools: [], permissionMode: 'dontAsk',
      canUseTool: async () => ({ behavior: 'deny', message: 'owned protocol fixture has no tools' }),
      mcpServers: {}, strictMcpConfig: true, settingSources: [], additionalDirectories: [],
      persistSession: false, abortController,
      env: {
        PATH: process.env.PATH,
        ANTHROPIC_API_KEY: 'owned-local-protocol-fixture',
        ANTHROPIC_BASE_URL: baseURL,
        CLAUDE_CONFIG_DIR: config,
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
        DISABLE_TELEMETRY: '1',
        DISABLE_ERROR_REPORTING: '1',
      },
      stderr: text => { stderr += text; },
    },
  })) {
    frames.push(JSON.parse(JSON.stringify(frame)));
  }
  const assistants = frames.filter(frame => frame.type === 'assistant');
  const result = frames.findLast(frame => frame.type === 'result');
  assert.equal(assistants.length, 2, JSON.stringify(frames));
  assert.deepEqual(assistants.map(frame => frame.message.id), ['msg_owned_multipart_usage', 'msg_owned_multipart_usage']);
  assert.deepEqual(assistants.map(frame => frame.message.content.map(block => block.type)), [['text'], ['text']]);
  assert.deepEqual(assistants.map(frame => frame.message.content[0].text), ['first independent block', 'second independent block']);
  for (const frame of assistants) {
    assert.equal(frame.message.usage.input_tokens, startUsage.input_tokens);
    assert.equal(frame.message.usage.cache_creation_input_tokens, startUsage.cache_creation_input_tokens);
    assert.equal(frame.message.usage.cache_read_input_tokens, startUsage.cache_read_input_tokens);
  }
  assert.equal(result?.subtype, 'success', JSON.stringify(result));
  assert.equal(result.usage.output_tokens, 17);
  const packageInfo = JSON.parse(await readFile(new URL('./node_modules/@anthropic-ai/claude-agent-sdk/package.json', import.meta.url), 'utf8'));
  const proof = {
    sdk_version: packageInfo.version,
    source: 'actual SDK and bundled CLI, served by an owned localhost SSE fixture; no paid model request',
    start_usage: startUsage,
    assistant_frames: assistants.map(frame => ({ id: frame.message.id, content: frame.message.content, usage: frame.message.usage })),
    result_usage: result.usage,
    requests,
    repeated_input_plus_creation: assistants.reduce((sum, frame) => sum + frame.message.usage.input_tokens + frame.message.usage.cache_creation_input_tokens, 0),
    once_per_step_input_plus_creation: startUsage.input_tokens + startUsage.cache_creation_input_tokens,
  };
  await writeFile(join(root, 'native-frames.json'), JSON.stringify(frames, null, 2) + '\n');
  console.log('CLAUDE_NATIVE_MULTIPART_USAGE ' + JSON.stringify(proof));
} catch (error) {
  console.error('CLAUDE_PROTOCOL_DIAGNOSTIC', JSON.stringify({ requests, frames, stderr: stderr.slice(-6000) }));
  throw error;
} finally {
  clearTimeout(timer);
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
