import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { gitProductsFromCommand, githubRepo } from '../subject/src/services/work-view/work-product.mjs';

const directory = mkdtempSync(join(tmpdir(), 'claude-github-ssh-'));
const work = join(directory, 'work'), remote = join(directory, 'remote.git');
const emptyConfig = join(directory, 'gitconfig'), shim = join(directory, 'ssh.mjs');
writeFileSync(emptyConfig, '');
writeFileSync(shim, "import { spawnSync } from 'node:child_process';\nconst result = spawnSync('git', ['receive-pack', process.env.TEST_GIT_REMOTE], { stdio: 'inherit' });\nprocess.exit(result.status ?? 1);\n");
const quote = text => "'" + text.replaceAll("'", "'\\''") + "'";
const env = {
  ...process.env, GIT_CONFIG_GLOBAL: emptyConfig, GIT_CONFIG_NOSYSTEM: '1',
  GIT_AUTHOR_NAME: 'Fixture', GIT_AUTHOR_EMAIL: 'fixture@example.invalid',
  GIT_COMMITTER_NAME: 'Fixture', GIT_COMMITTER_EMAIL: 'fixture@example.invalid',
  GIT_SSH_VARIANT: 'ssh', GIT_SSH_COMMAND: quote(process.execPath) + ' ' + quote(shim),
  TEST_GIT_REMOTE: remote,
};
const git = args => {
  const result = spawnSync('git', ['-c', 'commit.gpgsign=false', ...args], { env, encoding: 'utf8' });
  assert.equal(result.status, 0, JSON.stringify({ args, stdout: result.stdout, stderr: result.stderr }));
  return result;
};
try {
  git(['init', '--bare', remote]);
  git(['init', '-b', 'main', work]);
  let failures = 0;
  const urls = [
    'git@github.com:fixture-owner/fixture-repo.git',
    'ssh://git@github.com/fixture-owner/fixture-repo.git',
    'ssh://git@github.com:22/fixture-owner/fixture-repo.git',
    'ssh://git@ssh.github.com:443/fixture-owner/fixture-repo.git',
  ];
  for (const [index, url] of urls.entries()) {
    if (index === 0) git(['-C', work, 'remote', 'add', 'origin', url]);
    else git(['-C', work, 'remote', 'set-url', 'origin', url]);
    const subject = 'SSH transport evidence ' + index;
    writeFileSync(join(work, 'record.txt'), subject + '\n');
    git(['-C', work, 'add', 'record.txt']);
    const commit = git(['-C', work, 'commit', '-m', subject]);
    const pushed = git(['-C', work, 'push', 'origin', 'main']);
    const sha = git(['-C', work, 'rev-parse', 'HEAD']).stdout.trim();
    assert.equal(git(['--git-dir=' + remote, 'rev-parse', 'main']).stdout.trim(), sha);
    const response = { stdout: commit.stdout + pushed.stdout, stderr: commit.stderr + pushed.stderr };
    const output = response.stdout + '\n' + response.stderr;
    const products = gitProductsFromCommand('git commit -m "' + subject + '" && git push origin main', response, output);
    console.log('GIT_SSH_PRODUCTS', JSON.stringify({ remote: url, helper: githubRepo(url), pushOutput: pushed.stderr, products }));
    if (!products.some(product => product.kind === 'commit' && product.url === 'https://github.com/fixture-owner/fixture-repo/commit/' + sha)) failures++;
    if (!products.some(product => product.kind === 'branch' && product.url === 'https://github.com/fixture-owner/fixture-repo/tree/main')) failures++;
  }
  console.log('GIT_SSH_LINK_FAILURES', failures);
  if (failures) process.exitCode = 1;
} finally { rmSync(directory, { recursive: true, force: true }); }
