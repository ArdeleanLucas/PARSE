/**
 * PM2 ecosystem config for the PARSE API server on the PC (WSL2/Ubuntu).
 *
 * Usage (run once after each WSL cycle, or wire into `pm2 startup`):
 *
 *   pm2 start deploy/pm2-ecosystem.config.js
 *   pm2 save
 *
 * IMPORTANT — cwd must be the live workspace, NOT the git repo clone.
 * The server resolves annotation/audio paths relative to cwd. Running from
 * the repo clone causes annotation writes to land inside the git working
 * tree instead of the workspace directory.
 *
 * Known issue — branch auto-switching:
 *   Something on the PC (Hermes skill, cron, or another PM2 process) issues
 *   `git checkout` against /home/lucas/gh/ardeleanlucas/parse and switches it
 *   away from the desired branch between deployments. Until that is tracked
 *   down, verify the branch before restarting the server:
 *
 *     cd /home/lucas/gh/ardeleanlucas/parse && git branch --show-current
 *
 *   Expected: feat/ipa-forced-align-pipeline (or main after merge)
 */
module.exports = {
  apps: [
    {
      name: "parse-api",
      script: "/usr/bin/python3",
      args: "-u /home/lucas/gh/ardeleanlucas/parse/python/server.py --compute-mode=thread",
      // cwd MUST be the workspace, not the repo clone — see note above
      cwd: "/home/lucas/parse-workspace",
      env: {
        PARSE_WORKSPACE_ROOT: "/home/lucas/parse-workspace",
        PARSE_AI_CONFIG: "/home/lucas/parse-workspace/config/ai_config.json",
      },
    },
  ],
};
