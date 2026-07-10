// PARSE desktop model-registry client (§9.4 Gate B).
//
// Typed helpers over the backend model routes. Read routes
// (`GET /api/models`, `GET /api/models/{id}`) are already live; the
// install/delete/binding routes land with the §9.4 backend follow-up
// (PR #685). Every call goes through the shared client helpers — no
// component or store touches `fetch` directly, except the multipart
// pack upload, which follows the same bare-`fetch` pattern the other
// upload helpers in this folder use (see `importConceptsCsv` /
// `onboardSpeaker`) because `apiFetch` forces a JSON Content-Type that
// would break the multipart boundary.
import { apiFetch, networkError, resolveJobId } from "./shared";

export type ModelStage = "stt" | "ipa" | "ortho";
export type ModelFormat = "faster-whisper-ct2" | "hf-transformers";
/** Where a model physically lives on disk. */
export type ModelRoot = "bundled" | "user";
/** How a model was obtained. */
export type ModelSourceType = "bundled" | "user" | "hf";

export interface ModelSource {
  type: ModelSourceType;
  ref: string;
}

export interface ModelRecord {
  id: string;
  name: string;
  stage: ModelStage;
  format: ModelFormat;
  engine: string;
  languages: string[];
  source: ModelSource;
  /** Canonical byte size from the backend serializer. */
  size_bytes: number;
  /** User (removable) vs bundled (protected) models. */
  removable: boolean;
  root: ModelRoot;
  /** Present on the serializer but not required by the manager UI. */
  entrypoint_path?: string;
  version?: string;
}

/** Per-active-project stage → model-id assignment (null = unassigned). */
export interface ModelBinding {
  stt: string | null;
  ipa: string | null;
  ortho: string | null;
}

/** Install job handle. Poll via `pollCompute('model_install', jobId)`. */
export interface ModelInstallJob {
  jobId: string;
}

export interface InstallModelFromHfRequest {
  hfRepoId: string;
  stage: ModelStage;
  format: ModelFormat;
  name?: string;
}

const MODELS_PATH = "/api/models";
const INSTALL_PATH = "/api/models/install";
const BINDING_PATH = "/api/models/binding";

/** GET /api/models → the installed-model list (bundled + user). */
export async function listModels(): Promise<ModelRecord[]> {
  const payload = await apiFetch<{ models?: ModelRecord[] }>(MODELS_PATH);
  return Array.isArray(payload?.models) ? payload.models : [];
}

/** GET /api/models/{id} → a single record. Throws ApiError on 404. */
export async function getModel(id: string): Promise<ModelRecord> {
  return apiFetch<ModelRecord>(`${MODELS_PATH}/${encodeURIComponent(id)}`);
}

/**
 * POST /api/models/install (multipart) → 202 `{jobId}`.
 * Uploads a `.zip` / `.parsemodel` pack in the `pack` form field.
 */
export async function installModelPack(
  file: File,
  options: { overwrite?: boolean } = {},
): Promise<ModelInstallJob> {
  const form = new FormData();
  form.append("pack", file);
  if (options.overwrite) {
    form.append("overwrite", "true");
  }
  let response: Response;
  try {
    response = await fetch(INSTALL_PATH, { method: "POST", body: form });
  } catch (error) {
    throw networkError(INSTALL_PATH, { method: "POST" }, error);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API POST ${INSTALL_PATH} failed ${response.status}: ${text}`);
  }
  const payload = await response.json();
  return { jobId: resolveJobId(payload) };
}

/**
 * POST /api/models/install (JSON) → 202 `{jobId}`.
 * Fetches a model from a HuggingFace repo id.
 */
export async function installModelFromHf(
  request: InstallModelFromHfRequest,
): Promise<ModelInstallJob> {
  const payload = await apiFetch<unknown>(INSTALL_PATH, {
    method: "POST",
    body: JSON.stringify(request),
  });
  return { jobId: resolveJobId(payload) };
}

export interface DeleteModelResult {
  ok: boolean;
  id: string;
}

/** DELETE /api/models/{id} — synchronous; user models only. */
export async function deleteModel(id: string): Promise<DeleteModelResult> {
  return apiFetch<DeleteModelResult>(`${MODELS_PATH}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/** GET /api/models/binding → the active project's stage bindings. */
export async function getModelBinding(): Promise<ModelBinding> {
  const payload = await apiFetch<Partial<ModelBinding>>(BINDING_PATH);
  return {
    stt: payload?.stt ?? null,
    ipa: payload?.ipa ?? null,
    ortho: payload?.ortho ?? null,
  };
}

/**
 * POST /api/models/binding — assign (or clear, with `modelId === null`) the
 * model bound to a pipeline stage for the active project.
 */
export async function setModelBinding(
  stage: ModelStage,
  modelId: string | null,
): Promise<ModelBinding> {
  const payload = await apiFetch<Partial<ModelBinding>>(BINDING_PATH, {
    method: "POST",
    body: JSON.stringify({ stage, modelId }),
  });
  return {
    stt: payload?.stt ?? null,
    ipa: payload?.ipa ?? null,
    ortho: payload?.ortho ?? null,
  };
}
