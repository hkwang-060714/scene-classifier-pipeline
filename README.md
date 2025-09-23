# 图像场景分类器 (Image Scene Classifier)

这是一个利用先进视觉语言模型（Qwen-VL）对海量图像进行自动化场景分类的高效工具。它通过并行处理和断点续传机制，能稳定地从结构化的 `.jsonl` 文件中读取图片路径并输出分类结果，极大提升了数据处理的自动化程度和鲁棒性。

## 核心功能

*   **批量处理**：从 `.jsonl` 文件中读取图片路径，自动分类。
*   **智能分类**：调用云端 `Qwen2.5-VL-72B-Instruct` 模型，精准识别室内 / 城市 / 自然等场景。
*   **健壮可靠**：内置三级重试机制和详细的错误报告，确保处理稳定。
*   **高效快速**：支持多线程并行处理（默认 4 线程），显著缩短处理时间。
*   **断点续传**：自动保存进度，程序中断后可从中断处继续，避免重复劳动。

## 快速上手

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **准备输入**:
    确保您的 `.jsonl` 文件中每行都包含 `"storage_path"` 字段：
    ```json
    {"storage_path": "/path/to/your/image1.jpg"}
    {"storage_path": "/path/to/your/image2.png"}
    ```

3.  **运行脚本**:
    ```bash
    python classify_images_from_jsonl.py
    ```
    程序会提示您输入 `.jsonl` 文件的路径和其他处理参数。

4.  **查看输出**:
    结果默认保存在以下目录：
    `/inspire/hdd/project/embodied-multimodality/public/pywang/hkwang/data_wheel_the_first_task/`

## 技术实现与注意事项

*   **核心模型**: 本模块调用云端的 `Qwen2.5-VL-72B-Instruct` 大模型进行图像理解和分类，本地无需 GPU。
*   **健壮性设计**: 内置三级重试机制。首先使用主提示词，失败后尝试备用提示词（需提供 `prompt_engine_2.txt` 文件），并能处理网络超时、JSON 解析失败等多种异常。
*   **效率优化**: 支持多线程并行处理（默认 4 线程），可显著缩短总处理时间。
*   **断点续传**: 处理过程中会定期（默认每 100 张）将进度保存到 `resume_checkpoint.jsonl` 文件。若程序意外中断，重新运行时可自动从中断处继续。
*   **注意事项**:
    *   请确保 `INF_API_KEY` 环境变量已正确设置，否则无法调用 API。
    *   由于调用的是远程 API，处理速度受网络状况和 API 服务器负载影响。
    *   输入的 `.jsonl` 文件应确保路径正确且图片文件可访问，否则会被记录到错误列表中。

## 输出文件 JSON 结构详解 (Schema)

本模块所有输出文件均采用 **JSONL** 格式，即每行一个独立的 JSON 对象。

### 1. 主结果文件: `classification_results.jsonl`

包含所有图片的完整处理记录。

```json
{
  "index": 1,
  "image_info": {
    "filename": "image1.jpg",
    "full_path": "/absolute/path/to/image1.jpg",
    "subfolder": "from_jsonl",
    "relative_path": "/absolute/path/to/image1.jpg",
    "extension": ".jpg",
    "size": 102400
  },
  "classification_result": {
    "reasoning": "图片显示一个有沙发和茶几的房间...",
    "category": 1,
    "category_name": "Indoor",
    "confidence": "高",
    "status": "success"
  },
  "final_status": "success",
  "processed_at": "2024-05-28 10:30:45"
}
```

### 2. 错误报告文件: `failed_images_report.jsonl`

仅包含处理失败的图片记录。

```json
{
  "index": 5,
  "image_path": "/absolute/path/to/missing_image.png",
  "relative_path": "/absolute/path/to/missing_image.png",
  "status": "file_not_found",
  "error_message": "图片文件不存在: /absolute/path/to/missing_image.png",
  "processed_at": "2024-05-28 10:32:11"
}
```

### 3. 断点续传文件: `resume_checkpoint.jsonl`

用于在程序意外中断后恢复进度，通常只有一行。

```json
{
  "info": {
    "message": "This is a temporary file for resuming...",
    "saved_at": "2024-05-28 10:35:00",
    "total_processed_so_far": 100,
    "auto_save_interval": 100
  },
  "results": [
    { "index": 1, "image_info": { ... }, "classification_result": { ... }, ... },
    // ... 更多已处理图片的结果
    { "index": 100, "image_info": { ... }, "classification_result": { ... }, ... }
  ]
}
```

## 依赖与环境

*   **Python 版本**: 3.8 或更高版本。
*   **外部依赖**: 详见 `requirements.txt`。
