import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// ../ml/scripts/predict.py prints {"bin": "cans"|"organics"|"waste", "confidence": 0-1,
// "top3": [...]}. "bin" is literally the key rewardTable.ts looks up (see predict.py's
// own note: the model predicts a physical BIN, not a material).
export interface ClassificationResult {
  bin: string;
  confidence: number;
  top3: { bin: string; confidence: number }[];
}

const PREDICT_SCRIPT = new URL("../../ml/scripts/predict.py", import.meta.url).pathname;
const ML_VENV_PYTHON = new URL("../../ml/.venv/bin/python3", import.meta.url).pathname;

// predict.py needs onnxruntime/numpy/pillow, which only live in ml/.venv (see
// ml/README.md) — plain system "python3" on PATH won't have them.
const PYTHON = existsSync(ML_VENV_PYTHON) ? ML_VENV_PYTHON : "python3";

export async function classifyImage(imagePath: string): Promise<ClassificationResult> {
  const { stdout } = await execFileAsync(PYTHON, [PREDICT_SCRIPT, imagePath]);
  return JSON.parse(stdout) as ClassificationResult;
}
