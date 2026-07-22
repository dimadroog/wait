# demos_for_bc_ablation

H4 ([TASK_GEN1_POLICY_ABLATION](../../../../../../docs/tasks/archive/TASK_GEN1_POLICY_ABLATION.md)): `h4_filtered.npz` — BC без сегментов/семплов с доминированием пустого действия.

- Drop segment if noop_frac ≥ 0.5: seg_001.npz, seg_005.npz
- Kept segments: seg_002.npz, seg_003.npz, seg_004.npz
- Within kept: drop samples with empty action; n=781, noop_frac=0
- Loader: meta `prefer_embedded_actions: true` → `bc_pretrain` берёт `actions` из npz
