# 小鲸固定声线 v1

用户于 2026-11-08 试听后明确选定：“这个感觉太对了！声音就这样固定。”本目录的 `reference.wav` 是该次试听的原始 24kHz WAV，字节未修改；MP3 试听由同一 WAV 编码。参考文本、SHA-256、合成提示及运行模型版本见 `voice.json`。

该声音由 [Qwen3-TTS VoiceDesign](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit) 原创合成。风格方向由用户提供的[《干饭妹小鲸》](https://www.bilibili.com/video/BV15j4M6UE5R/)启发；没有提取或克隆该视频的音轨，也没有把本音色标为其原版配音。

后续台词使用 [Qwen3-TTS Base 4bit](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit)，以这份已选定参考音频和文本进行固定声线合成。两个模型的模型卡均标注 Apache-2.0；运行实现使用 [MLX Audio](https://github.com/Blaizzy/mlx-audio)，当前独立环境版本 0.6.4。权重仅缓存在本地，不加入 Git。

这份参考音频现为运行所需的正式角色资源，纳入版本管理；它不属于临时试听文件。其他候选、生成的台词音频和试听记录继续保存在 Git 忽略目录。不得覆盖此参考、重新设计声线或改回 Edge 晓伊；如用户以后要求换声线，应新增音色版本并另行试听。
