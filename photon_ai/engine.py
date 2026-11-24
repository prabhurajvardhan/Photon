import os, numpy as np, onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

DEFAULT_HF_REPO = "prabhurajvardhan/photon-v0-int4"
N_KV_SLOTS = 14

class TinyCodeEngine:
    def __init__(self, onnx_path: str = None, tokenizer_path: str = None):
        onnx_path = onnx_path or hf_hub_download(repo_id=DEFAULT_HF_REPO, filename="photon_v0_kvcached_int4.onnx")
        tokenizer_path = tokenizer_path or hf_hub_download(repo_id=DEFAULT_HF_REPO, filename="code_patch_8k_tokenizer.json")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = min(4, os.cpu_count() or 1)
        self.sess = ort.InferenceSession(onnx_path, opts, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(tokenizer_path)
        self.pad_id, self.unk_id, self.bos_id, self.eos_id = [self.tok.token_to_id(t) for t in ("<|pad|>", "<|unk|>", "<|bos|>", "<|eos|>")]

    def _argmax_m(self, lg: np.ndarray) -> int:
        lg[self.pad_id] = -1e9; lg[self.unk_id] = -1e9; lg[self.bos_id] = -1e9
        return int(np.argmax(lg))

    def generate_patch(self, lang: str, error_msg: str, full_ctx: str, broken_fn: str, max_tokens: int = 96) -> str:
        tag = "<|lang_py|>" if lang == "py" else "<|lang_ts|>"
        prompt = f"<|bos|>{tag}<|err|>\n{error_msg}\n<|ctx|>\n{full_ctx}\n<|think|><|end_think|>\n<|search|>\n{broken_fn}\n<|replace|>\n"
        ids = self.tok.encode(prompt).ids[:1024]
        P = len(ids)
        p_mask = np.triu(np.full((1, 1, P, P), -1e9, dtype=np.float32), k=1)
        pk = np.zeros((1, N_KV_SLOTS, 10, 0, 64), dtype=np.float32)
        pv = np.zeros((1, N_KV_SLOTS, 10, 0, 64), dtype=np.float32)
        m_lg, m0, m1, m2, pk, pv = self.sess.run(None, {"input_ids": np.array([ids], dtype=np.int64), "pos_ids": np.arange(0, P, dtype=np.int64)[None, :], "attn_mask": p_mask, "past_ks": pk, "past_vs": pv})
        cur_pos, gen = P, []
        step_mask = np.triu(np.full((4, 4), -1e9, dtype=np.float32), k=1)

        while len(gen) < max_tokens and cur_pos + 4 < 4096:
            t1, t2, t3, t4 = [self._argmax_m(x[0, -1].copy()) for x in (m_lg, m0, m1, m2)]
            d_mask = np.concatenate([np.zeros((1, 1, 4, cur_pos), dtype=np.float32), step_mask[None, None, :, :]], axis=-1)
            v_lg, v_m0, v_m1, v_m2, new_pk, new_pv = self.sess.run(None, {"input_ids": np.array([[t1, t2, t3, t4]], dtype=np.int64), "pos_ids": np.arange(cur_pos, cur_pos + 4, dtype=np.int64)[None, :], "attn_mask": d_mask, "past_ks": pk, "past_vs": pv})
            lg0, lg1, lg2, _ = v_lg.reshape(4, -1).copy()
            acc = [t1]
            if self._argmax_m(lg0) == t2:
                acc.append(t2)
                if self._argmax_m(lg1) == t3:
                    acc.append(t3)
                    if self._argmax_m(lg2) == t4:
                        acc.append(t4)
            n_acc = len(acc)
            gen.extend(acc)
            pk, pv = new_pk[:, :, :, :cur_pos + n_acc, :], new_pv[:, :, :, :cur_pos + n_acc, :]
            cur_pos += n_acc
            if self.eos_id in acc:
                gen = gen[:gen.index(self.eos_id)]
                break
            idx_l = n_acc - 1
            m_lg, m0, m1, m2 = v_lg[:, idx_l:idx_l+1, :], v_m0[:, idx_l:idx_l+1, :], v_m1[:, idx_l:idx_l+1, :], v_m2[:, idx_l:idx_l+1, :]
        return next(iter(self.tok.decode(gen, skip_special_tokens=False).split("<|end_patch|>")), "").strip()
