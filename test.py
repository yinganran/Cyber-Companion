import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"  # 国内镜像

from transformers import AutoProcessor, AutoModel
local_dir = r"D:\ai_models\qwen"
processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-Omni-7B", cache_dir=local_dir)
model = AutoModel.from_pretrained("Qwen/Qwen2.5-Omni-7B", cache_dir=local_dir)