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
      // Compute mode:
      //   --compute-mode=thread       legacy, default. Works on Linux native;
      //                               wedges under heavy wav2vec2 loads on WSL2.
      //   --compute-mode=subprocess   one fresh process per job. Stable but
      //                               pays ~60s Aligner.load() per speaker.
      //   --compute-mode=persistent   single long-lived worker, Aligner loaded
      //                               once (2026-04 rollout). Flip here after
      //                               the rollout checklist in the PR passes
      //                               on Fail02.
      args: "-u /home/lucas/gh/ardeleanlucas/parse/python/server.py --compute-mode=thread",
      // cwd MUST be the workspace, not the repo clone — see note above
      cwd: "/home/lucas/parse-workspace",
      env: {
        PARSE_WORKSPACE_ROOT: "/home/lucas/parse-workspace",
        PARSE_AI_CONFIG: "/home/lucas/parse-workspace/config/ai_config.json",
        OMP_NUM_THREADS: "1",
        MKL_NUM_THREADS: "1",
        OPENBLAS_NUM_THREADS: "1",
        VECLIB_MAXIMUM_THREADS: "1",
        NUMEXPR_NUM_THREADS: "1",
        // WSL2 GPU passthrough crashes the VM under sustained ML workloads,
        // even on Whisper STT/ORTH (not just wav2vec2). Force everything
        // to CPU until the WSL/dxg stability issue is resolved.
        PARSE_STT_FORCE_CPU: "1",
        CUDA_VISIBLE_DEVICES: "",
        // Alternative opt-in route (equivalent to --compute-mode=persistent).
        // Leave unset while rolling out; set to "true" to opt in without
        // editing the args line above. The CLI flag wins if both are set.
        // PARSE_USE_PERSISTENT_WORKER: "true",
      },
    },
  ],
};
