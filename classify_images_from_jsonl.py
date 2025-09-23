import base64
import json
import os
from openai import OpenAI
import time
import re
from pathlib import Path
import concurrent.futures
from threading import Lock
import threading
import random

# 设置环境变量
INF_API_KEY = "IiW1LZ0OEZU7cb37E7/1pP75wZXEsC2Wa/f6qToo+SI="
if not os.getenv("INF_API_KEY"):
    os.environ["INF_API_KEY"] = INF_API_KEY

# 用于线程安全的打印
print_lock = Lock()
def thread_safe_print(*args, **kwargs):
    """线程安全的打印函数"""
    with print_lock:
        print(*args, **kwargs)

def load_system_prompt(prompt_file_path="prompt_engine.txt"):
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 如果prompt_file_path是相对路径，则相对于当前脚本目录
    if not os.path.isabs(prompt_file_path):
        prompt_file_path = os.path.join(current_dir, prompt_file_path)
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read().strip()
        if not system_prompt:
            raise ValueError("提示词文件为空")
        print(f"成功加载系统提示词: {prompt_file_path}")
        return system_prompt
    except FileNotFoundError:
        error_msg = f"提示词文件不存在: {prompt_file_path}"
        print(f"错误: {error_msg}")
        # 返回您提供的新提示词作为备用
        new_prompt = """You are an image analysis expert. Your task is to classify each image by its physical setting.
Instructions:
1. First, describe what you see — note the key visual elements like objects, lighting, spatial layout, and environmental features that help you identify the setting.
2. Then, choose the best category from these five options:
   - 1: Indoor — Shows interior spaces like rooms, hallways, or enclosed areas with artificial lighting and furniture.
   - 2: Urban/Built Environment — Shows outdoor human-made spaces like streets, buildings, bridges, or city areas (without dominant natural features).
   - 3: Natural Landscape — Shows outdoor natural settings like forests, mountains, oceans, or wilderness (with little to no human construction).
   - 4: No Clear Setting — The image doesn't provide enough visual context to determine a physical space. This includes abstract graphics, isolated objects, text-only images, or UI elements.
   - 5: Multiple Scenes — Only for composite images (split-screen, collages, overlays, etc.). First check: if any part shows "No Clear Setting" → classify as "4". If all parts can be clearly assigned to categories 1-3 → classify as "5".
3. Set your confidence level: High / Medium / Low — based on how clear and obvious the visual evidence is.
Important Guidelines:
- Only classify what you can actually see — don't guess or assume context
- Base your decision purely on visual spatial cues
- For category 5, the image must have a composite layout — don't use this just because you see mixed elements (like a tree in a city photo)
- Always explain your reasoning first before choosing a category
Output Format (JSON only):
```json
{
  "reasoning": "[Describe the key visual features that indicate the type of space or lack thereof]",
  "category": [1-5],
  "category_name": "[Exact category name from above]",
  "confidence": "[High/Medium/Low]"
}
```"""
        print(f"警告: 使用您提供的新提示词")
        return new_prompt
    except Exception as e:
        error_msg = f"读取提示词文件失败: {str(e)}"
        print(f"错误: {error_msg}")
        # 返回您提供的新提示词
        new_prompt = """You are an image analysis expert. Your task is to classify each image by its physical setting.
Instructions:
1. First, describe what you see — note the key visual elements like objects, lighting, spatial layout, and environmental features that help you identify the setting.
2. Then, choose the best category from these five options:
   - 1: Indoor — Shows interior spaces like rooms, hallways, or enclosed areas with artificial lighting and furniture.
   - 2: Urban/Built Environment — Shows outdoor human-made spaces like streets, buildings, bridges, or city areas (without dominant natural features).
   - 3: Natural Landscape — Shows outdoor natural settings like forests, mountains, oceans, or wilderness (with little to no human construction).
   - 4: No Clear Setting — The image doesn't provide enough visual context to determine a physical space. This includes abstract graphics, isolated objects, text-only images, or UI elements.
   - 5: Multiple Scenes — Only for composite images (split-screen, collages, overlays, etc.). First check: if any part shows "No Clear Setting" → classify as "4". If all parts can be clearly assigned to categories 1-3 → classify as "5".
3. Set your confidence level: High / Medium / Low — based on how clear and obvious the visual evidence is.
Important Guidelines:
- Only classify what you can actually see — don't guess or assume context
- Base your decision purely on visual spatial cues
- For category 5, the image must have a composite layout — don't use this just because you see mixed elements (like a tree in a city photo)
- Always explain your reasoning first before choosing a category
Output Format (JSON only):
```json
{
  "reasoning": "[Describe the key visual features that indicate the type of space or lack thereof]",
  "category": [1-5],
  "category_name": "[Exact category name from above]",
  "confidence": "[High/Medium/Low]"
}
```"""
        print(f"警告: 使用您提供的新提示词")
        return new_prompt

def limited_robust_parse_classification_result(content):
    """
    仅使用直接解析、Markdown代码块和智能括号匹配三种方法解析JSON
    """
    if not content:
        return {"error": "空内容"}
    # 预处理：统一编码和格式
    content = content.strip()
    # 方法1: 直接解析标准JSON
    try:
        result = json.loads(content)
        return result
    except json.JSONDecodeError:
        pass
    # 方法2: 查找并解析markdown代码块
    try:
        # 支持多种代码块格式
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'`json\s*(\{.*?\})\s*`',
            r'`(\{.*?\})`'
        ]
        for pattern in json_patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                json_str = match.group(1)
                result = json.loads(json_str)
                return result
    except json.JSONDecodeError:
        pass
    # 方法3: 智能括号匹配（改进版）
    try:
        brace_count = 0
        start_pos = -1
        end_pos = -1
        in_string = False
        escape_next = False
        for i, char in enumerate(content):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char in ['"', "'"]:
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    if start_pos == -1:
                        start_pos = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_pos != -1:
                        end_pos = i
                        break
        if start_pos != -1 and end_pos != -1:
            json_str = content[start_pos:end_pos + 1]
            result = json.loads(json_str)
            return result
    except json.JSONDecodeError:
        pass
    # 如果三种方法都失败，返回错误信息
    return {
        "error": "JSON解析失败（直接解析、Markdown代码块、智能括号匹配均失败）",
        "raw_content": content[:500] + "..." if len(content) > 500 else content
    }

# 保留的标准化函数
def normalize_classification_result(result):
    if "error" in result:
        return result
    category = result.get("category")
    category_name = result.get("category_name", "")
    confidence = result.get("confidence", "未知")
    reasoning = result.get("reasoning", "")
    # 标准化分类名称映射
    category_name_variations = {
        1: ["室内", "室内场景", "indoor", "interior", "屋内", "房间内", "建筑内部", "Indoor"],
        2: ["室外人造", "室外人造场景", "人造", "人工环境", "outdoor artificial", "urban", "城市", "街道", "Urban/Built Environment"],
        3: ["室外自然", "室外自然场景", "自然", "自然环境", "outdoor natural", "nature", "风景", "景观", "Natural Landscape"],
        4: ["无场景", "无场景内容", "无场景信息", "non-scene", "abstract", "文字", "图表", "绘画", "插画", "No Clear Setting"],
        5: ["混合", "混合场景", "拼接", "组合", "mixed", "composite", "多场景", "合成", "Multiple Scenes"]
    }
    # 处理无效的category值
    if category in [0, None, "0", "null", ""]:
        # 根据category_name推断分类
        category_name_lower = category_name.lower().strip()
        for cat_id, variations in category_name_variations.items():
            for variation in variations:
                # 改进匹配逻辑，支持部分包含
                if variation.lower() in category_name_lower or category_name_lower in variation.lower():
                    category = cat_id
                    break
            if category not in [0, None, "0", "null", ""]:
                break
        # 如果仍然无法推断，标记为不确定
        if category in [0, None, "0", "null", ""]:
            return {
                "category": None,
                "category_name": "无法分类",
                "confidence": confidence,
                "reasoning": reasoning or "无法从提供的信息中确定场景类型",
                "status": "uncertain"
            }
    # 确保category是有效的整数值
    try:
        category = int(category)
        if category not in [1, 2, 3, 4, 5]:
            return {
                "category": None,
                "category_name": f"无效分类编号: {category}",
                "confidence": confidence,
                "reasoning": reasoning,
                "status": "invalid_category"
            }
    except (ValueError, TypeError):
        return {
            "category": None,
            "category_name": "分类格式错误",
            "confidence": confidence,
            "reasoning": reasoning,
            "status": "format_error"
        }
    # 标准化category_name
    if not category_name or category_name.strip() == "":
        standard_names = {
            1: "Indoor",
            2: "Urban/Built Environment",
            3: "Natural Landscape",
            4: "No Clear Setting",
            5: "Multiple Scenes"
        }
        category_name = standard_names.get(category, "未知分类")
    # 标准化confidence值
    confidence_mapping = {
        "high": "高", "medium": "中", "low": "低",
        "确定": "高", "可能": "中", "不确定": "低",
        "明确": "高", "一般": "中", "模糊": "低",
        "High": "高", "Medium": "中", "Low": "低"
    }
    confidence_lower = str(confidence).lower().strip()
    for key, value in confidence_mapping.items():
        # 改进匹配逻辑，支持部分包含
        if key.lower() in confidence_lower:
            confidence = value
            break
    # 确保confidence是标准值
    if confidence not in ["高", "中", "低"]:
        confidence = "未知"
    # 清理和验证reasoning
    if not reasoning or reasoning.strip() == "":
        reasoning = f"图像被分类为{category_name}"
    else:
        # 限制reasoning长度，避免过长
        if len(reasoning) > 500:
            reasoning = reasoning[:497] + "..."
    return {
        "reasoning": reasoning,     
        "category": category,
        "category_name": category_name,
        "confidence": confidence,
        "status": "success"
    }

# --- 修改后的分类单张图片函数 ---
def classify_single_image(image_path: str, max_retries: int = 3, system_prompt: str = None):
    """分类单个图片 - 使用新的API端点和修改后的JSON处理逻辑"""
    # 更新API配置
    API_KEY = INF_API_KEY
    BASE_URL = "https://gqp5d559gdqdcbqjhedppj9k58qgcepa.openapi-qb.sii.edu.cn/v1"
    MODEL = "Qwen2.5-VL-72B-Instruct"
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        # 如果没有提供系统提示词，则加载默认的（现在是您提供的新提示词）
        if system_prompt is None:
            system_prompt = load_system_prompt()
        user_prompt = "请分析这张图片属于哪种场景类型。"
        # 1. 首先使用主提示词进行尝试
        for attempt in range(max_retries):
            try:
                # 调用模型 API (使用 primary prompt)
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        # 修正了 URL 格式，移除了 'data:'
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    temperature=0.1,
                    timeout=60  # 增加超时时间
                )
                content = response.choices[0].message.content
                # 尝试解析响应 (使用仅限方法1-3的解析器)
                raw_result = limited_robust_parse_classification_result(content)
                # 检查解析结果
                if "error" not in raw_result:
                    # 如果解析成功，进行标准化
                    result = normalize_classification_result(raw_result)
                    # 检查标准化后结果
                    if result.get("status") == "success":
                        return result
                    else:
                        # 标准化失败，记录日志，但不立即返回错误，继续重试
                        thread_safe_print(f"    第 {attempt + 1} 次尝试 - 解析成功但标准化失败: {result.get('error', 'Unknown error')}")
                else:
                    # 解析失败，记录日志
                    thread_safe_print(f"    第 {attempt + 1} 次尝试 - 解析失败: {raw_result.get('error', 'Unknown error')}")
                # 如果是最后一次重试，则准备尝试备用提示词
                if attempt == max_retries - 1:
                    thread_safe_print(f"    主提示词重试 {max_retries} 次后仍失败, 准备尝试备用提示词...")
                else:
                    # 如果不是最后一次重试，等待后重试
                    wait_time = (attempt + 1) * 5
                    thread_safe_print(f"    第 {attempt + 1} 次尝试失败, 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
            except Exception as e: # 捕获 JSON 解析错误、标准化错误或 API 调用错误
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    thread_safe_print(f"    第 {attempt + 1} 次 API 调用或处理失败 ({e}), 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    # 如果主提示词所有重试都失败，记录并准备尝试备用提示词
                    thread_safe_print(f"    主提示词重试 {max_retries} 次后仍失败 ({e}), 准备尝试备用提示词...")
        # 2. 如果主提示词所有重试都失败，尝试备用提示词
        try:
            # 加载备用提示词
            backup_prompt = load_system_prompt("prompt_engine_2.txt")
            thread_safe_print(f"    正在使用备用提示词调用 API...")
            # 使用备用提示词调用 API
            response_backup = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": backup_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    # 修正了 URL 格式，移除了 'data:'
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.1,
                timeout=60
            )
            content_backup = response_backup.choices[0].message.content
            # 使用仅限方法1-3的解析器再次尝试解析
            raw_result_backup = limited_robust_parse_classification_result(content_backup)
            if "error" not in raw_result_backup:
                result_backup = normalize_classification_result(raw_result_backup)
                if result_backup.get("status") == "success":
                    thread_safe_print(f"    使用备用提示词成功解析!")
                    return result_backup
                else:
                    thread_safe_print(f"    使用备用提示词解析成功但标准化失败: {result_backup}")
            else:
                 thread_safe_print(f"    使用备用提示词解析也失败: {raw_result_backup.get('error', 'Unknown error')}")
        except Exception as backup_error:
            thread_safe_print(f"    加载或使用备用提示词时出错: {backup_error}")
        # 3. 如果备用提示词也失败，返回最终错误
        return {
            "error": f"主提示词和备用提示词均尝试失败。主提示词最后错误: {raw_result.get('error', 'N/A') if 'raw_result' in locals() else 'N/A'} | 备用提示词错误: {str(backup_error) if 'backup_error' in locals() else '加载或调用备用提示词失败'}",
            "raw_content": (content[:500] + "...") if 'content' in locals() and content and len(content) > 500 else content,
            "status": "parsing_failed_after_all_retries_and_backup"
        }
    except FileNotFoundError:
        return {"error": f"图片文件不存在: {image_path}", "status": "file_not_found"}
    except Exception as e:
        return {"error": f"处理出错: {str(e)}", "status": "processing_error"}

# --- 从 JSONL 文件加载图片路径 ---
def get_image_files_from_jsonl(jsonl_file_path: str):
    """
    从 JSONL 文件中读取图片文件路径。
    假设 JSONL 文件的每一行是一个 JSON 对象，其中包含一个 "storage_path" 字段。
    Args:
        jsonl_file_path: JSONL 文件的完整路径
    Returns:
        一个列表，包含所有图片的信息字典，每个字典至少包含 "full_path" 键。
    """
    if not os.path.exists(jsonl_file_path):
        print(f"错误: JSONL 文件不存在: {jsonl_file_path}")
        return []

    image_list = []
    try:
        with open(jsonl_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line: # 跳过空行
                    continue
                try:
                    data = json.loads(line)
                    # 根据您的示例，路径存储在 "storage_path" 字段中
                    image_path = data.get("storage_path")
                    if not image_path:
                        print(f"警告: 第 {line_num} 行缺少 'storage_path' 字段，已跳过。")
                        continue
                    if not os.path.exists(image_path):
                        print(f"警告: 第 {line_num} 行指定的图片文件不存在: {image_path}")
                        # 选择跳过不存在的文件
                        continue

                    # 构建图片信息字典
                    image_info = {
                        "filename": os.path.basename(image_path), # 从路径中提取文件名
                        "full_path": image_path, # 这是最关键的字段
                        "subfolder": "from_jsonl", # 由于没有文件夹结构，设为固定值
                        "relative_path": image_path, # 为了兼容，这里直接用完整路径
                        "extension": os.path.splitext(image_path)[1].lower(),
                        "size": os.path.getsize(image_path)
                    }
                    image_list.append(image_info)

                except json.JSONDecodeError as e:
                    print(f"错误: 第 {line_num} 行不是有效的JSON格式: {e}")
                    continue # 跳过无效行

        print(f"成功从 {jsonl_file_path} 加载 {len(image_list)} 个有效图片路径。")
        return image_list

    except Exception as e:
        print(f"读取 JSONL 文件时发生错误: {e}")
        return []

# --- 修改后的主处理函数 ---
def process_images_hierarchical_parallel_sampled(root_folder_path: str, output_dir: str = None,
                                                sample_count: int = 2, sample_method: str = "random",
                                                start_from: int = 1, max_images: int = None,
                                                max_workers: int = 4, auto_save_interval: int = 100): # 新增参数
    """
    并行处理图片 (带断点续传和自动保存)
    Args:
        root_folder_path: JSONL 文件路径 (为了兼容性保留参数名，但实际用途已变)
        output_dir: 输出目录
        sample_count: 不再使用，保留参数名以兼容调用
        sample_method: 不再使用，保留参数名以兼容调用
        start_from: 从第几张开始处理
        max_images: 最多处理多少张
        max_workers: 并行线程数
        auto_save_interval: 自动保存的间隔（处理多少张后保存一次），默认100
    """
    print(f"正在从 JSONL 文件加载图片路径: {root_folder_path}")
    # 加载系统提示词（在主进程中加载一次）
    system_prompt = load_system_prompt()
    # 从 JSONL 文件加载图片列表
    all_images = get_image_files_from_jsonl(root_folder_path)
    if not all_images:
        print("未从 JSONL 文件中找到任何有效的图片路径")
        return {}, {}

    total_sampled_files = len(all_images)
    total_original_files = total_sampled_files # 假设 JSONL 里的就是全部要处理的图片
    print(f"从 JSONL 文件加载了 {total_sampled_files} 张图片。")

    # 应用起始位置和数量限制
    if start_from > 1:
        all_images = all_images[start_from-1:]
        print(f"从第 {start_from} 张图片开始处理")
    if max_images:
        all_images = all_images[:max_images]
        print(f"限制处理 {max_images} 张图片")
    print(f"实际处理 {len(all_images)} 张图片")
    print(f"使用 {max_workers} 个并行线程")
    print()

    # --- 断点续传和自动保存准备 ---
    # 使用固定文件名
    temp_file_name = "resume_checkpoint.json"  # <<<--- 固定的断点续传文件名
    temp_file_path = os.path.join(output_dir or os.path.dirname(root_folder_path), temp_file_name)
    partial_results_lock = Lock() # 用于保护临时文件写入的锁
    loaded_partial_data = load_partial_results(temp_file_path)
    processed_indices_set = set() # 用于快速查找已处理的索引
    initial_results_list = []
    initial_success_count = 0
    initial_category_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    # 初始化子文件夹结果统计 (简化版，因为所有图片来自同一个 "虚拟" 文件夹)
    initial_subfolder_results = {
        "from_jsonl": {
            "results": [],
            "category_counts": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "success_count": 0,
            "uncertain_count": 0,
            "error_count": 0,
            "file_not_found_count": 0,
            "original_count": total_original_files,
            "sample_count": total_sampled_files,
            "sample_method": "n/a"
        }
    }

    if loaded_partial_data:
        initial_results_list = loaded_partial_data.get("results", [])
        # 重建已处理索引集合和初始计数器
        for res in initial_results_list:
            idx = res.get("index")
            if idx is not None:
                processed_indices_set.add(idx)
                # 更新计数器
                status = res.get("final_status", "unknown")
                if status == "success":
                     initial_success_count += 1
                     cat = res.get("classification_result", {}).get('category', 0)
                     if cat in initial_category_counts:
                         initial_category_counts[cat] += 1
                     sf = res.get("image_info", {}).get("subfolder", "")
                     if sf in initial_subfolder_results and cat in initial_subfolder_results[sf]["category_counts"]:
                         initial_subfolder_results[sf]["category_counts"][cat] += 1
                         initial_subfolder_results[sf]["success_count"] += 1
        print(f"[信息] 已跳过 {len(processed_indices_set)} 个已完成的任务。")

    # --- 准备并行处理的参数 ---
    process_args = []
    for i, image_info in enumerate(all_images):
        process_index = start_from + i
        # *** 断点续传关键点：跳过已处理的 ***
        if process_index in processed_indices_set:
            continue
        process_args.append((image_info, process_index, len(all_images), system_prompt))

    if not process_args:
        print("[信息] 所有任务似乎都已完成，无需进一步处理。")
        return {}, {}

    print(f"实际处理 {len(process_args)} 张图片 (已跳过 {len(processed_indices_set)} 张)")
    print(f"使用 {max_workers} 个并行线程")
    print()

    # 统计变量 (初始化为断点续传加载的值)
    category_counts = initial_category_counts
    subfolder_results = initial_subfolder_results
    success_count = initial_success_count
    uncertain_count = 0
    error_count = 0
    file_not_found_count = 0

    # 创建输出目录
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 创建详细日志文件
    log_file = os.path.join(output_dir or os.path.dirname(root_folder_path), f"classification_log_from_jsonl.txt")

    # --- 开始并行处理 ---
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {}
        for args in process_args:
            future = executor.submit(process_single_image_hierarchical, args)
            future_to_index[future] = args[1]  # process_index

        # 收集结果
        processed_count = len(initial_results_list) # 从已处理的数量开始计数
        results_list = initial_results_list # 从加载的结果开始
        last_save_count = processed_count # 记录上次保存时的计数

        for future in concurrent.futures.as_completed(future_to_index):
            try:
                result = future.result()
                results_list.append(result) # 添加新结果
                processed_count += 1

                # 更新统计
                status = result["final_status"]
                subfolder = result["image_info"]["subfolder"]

                # 全局统计
                if status == "success":
                    success_count += 1
                    category = result["classification_result"].get('category', 0)
                    if category in category_counts:
                        category_counts[category] += 1
                        if subfolder in subfolder_results and category in subfolder_results[subfolder]["category_counts"]:
                            subfolder_results[subfolder]["category_counts"][category] += 1
                        if subfolder in subfolder_results:
                            subfolder_results[subfolder]["success_count"] += 1
                elif status in ["uncertain", "invalid_category", "format_error"]:
                    uncertain_count += 1
                    if subfolder in subfolder_results: subfolder_results[subfolder]["uncertain_count"] += 1
                elif status == "file_not_found":
                    file_not_found_count += 1
                    if subfolder in subfolder_results: subfolder_results[subfolder]["file_not_found_count"] += 1
                else:
                    error_count += 1
                    if subfolder in subfolder_results: subfolder_results[subfolder]["error_count"] += 1

                # 添加到子文件夹结果中
                if subfolder in subfolder_results:
                    subfolder_results[subfolder]["results"].append(result)

                # 每处理完5个显示进度
                if processed_count % 5 == 0:
                    thread_safe_print(f"\n进度: {processed_count}/{len(all_images) + len(processed_indices_set)} - 成功: {success_count}, 不确定: {uncertain_count}, 文件未找到: {file_not_found_count}, 错误: {error_count}\n")

                # *** 自动保存关键点 ***
                if processed_count - last_save_count >= auto_save_interval:
                    print(f"[信息] 达到自动保存点 ({processed_count} 张)，正在保存部分结果...")
                    # 准备要保存的部分数据
                    temp_data_to_save = {
                        "info": {
                            "message": "This is a temporary file for resuming. Final results are in the main JSON file.",
                            "saved_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                            "total_processed_so_far": processed_count,
                            "auto_save_interval": auto_save_interval
                        },
                        "results": results_list # 保存到目前为止的所有结果
                    }
                    save_partial_results(temp_data_to_save, temp_file_path, partial_results_lock)
                    last_save_count = processed_count
                    print("[信息] 部分结果保存完成。")

            except Exception as exc:
                index = future_to_index.get(future, "Unknown")
                thread_safe_print(f"[{index}] 处理异常: {exc}")
                error_count += 1

        # 循环结束后，最后一次保存（如果自上次保存后有新增）
        if processed_count > last_save_count:
             print(f"[信息] 处理完成，正在保存最终部分结果...")
             temp_data_to_save = {
                 "info": { "message": "...", "saved_at": time.strftime('%Y-%m-%d %H:%M:%S'), "total_processed_so_far": processed_count },
                 "results": results_list
             }
             save_partial_results(temp_data_to_save, temp_file_path, partial_results_lock)
             print("[信息] 最终部分结果保存完成。")

    end_time = time.time()

    # --- 后处理和保存最终结果 ---
    # 按索引排序结果
    results_list.sort(key=lambda x: x["index"])
    # 构建结果字典
    all_results = {}
    for result in results_list:
        relative_path = result["image_info"]["relative_path"]
        all_results[relative_path] = result
    # 按子文件夹排序结果
    for subfolder_name in subfolder_results:
        subfolder_results[subfolder_name]["results"].sort(key=lambda x: x["index"])

    # 写入日志文件
    with open(log_file, 'w', encoding='utf-8') as log:
        log.write(f"图片分类日志 - 从JSONL文件加载\n")
        log.write(f"处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"源JSONL文件: {root_folder_path}\n")
        log.write(f"图片总数: {total_original_files}\n")
        log.write(f"实际处理数: {len(all_images) + len(processed_indices_set)}\n") # 包含已处理的
        log.write(f"起始位置: {start_from}\n")
        log.write(f"并行线程数: {max_workers}\n")
        log.write(f"总耗时: {end_time - start_time:.2f} 秒\n")
        log.write(f"平均每张: {(end_time - start_time)/(len(all_images) + len(processed_indices_set)):.2f} 秒\n") # 包含已处理的
        log.write(f"分类标准: 1-Indoor, 2-Urban/Built Environment, 3-Natural Landscape, 4-No Clear Setting, 5-Multiple Scenes\n")
        log.write("=" * 80 + "\n")

        # 全局分类统计
        log.write("全局各类别统计:\n")
        log.write(f"Indoor: {category_counts[1]}\n")
        log.write(f"Urban/Built Environment: {category_counts[2]}\n")
        log.write(f"Natural Landscape: {category_counts[3]}\n")
        log.write(f"No Clear Setting: {category_counts[4]}\n")
        log.write(f"Multiple Scenes: {category_counts[5]}\n")

        # 写入详细结果
        log.write("\n" + "=" * 80 + "\n")
        log.write("详细分类结果:\n")
        log.write("=" * 80 + "\n")
        for result in results_list:
            classification = result["classification_result"]
            image_info = result["image_info"]
            log.write(f"[{result['index']:03d}] {image_info['relative_path']}\n")
            log.write(f"     文件大小: {image_info['size']/1024:.1f}KB\n")
            log.write(f"     状态: {result['final_status']}\n")
            log.write(f"     分类: {classification.get('category_name', '未知')}\n")
            log.write(f"     置信度: {classification.get('confidence', '未知')}\n")
            # 显示完整推理内容，如果太长则适当截断
            reasoning_text = classification.get('reasoning', '无')
            if len(reasoning_text) > 200:
                log.write(f"     推理: {reasoning_text[:200]}...\n")
            else:
                log.write(f"     推理: {reasoning_text}\n")
            if "error" in classification:
                log.write(f"     错误: {classification.get('error', '未知')}\n")
                if 'raw_content' in classification:
                    log.write(f"     原始内容: {classification['raw_content'][:200]}...\n")
            log.write(f"     处理时间: {result['processed_at']}\n")
            log.write("\n")

        # 写入汇总统计
        log.write("\n" + "=" * 80 + "\n")
        log.write("处理汇总:\n")
        log.write(f"图片总数: {total_original_files}\n")
        log.write(f"实际处理数: {len(all_images) + len(processed_indices_set)}\n") # 包含已处理的
        log.write(f"成功分类: {success_count}\n")
        log.write(f"不确定分类: {uncertain_count}\n")
        log.write(f"文件未找到: {file_not_found_count}\n")
        log.write(f"处理错误: {error_count}\n")
        log.write(f"总耗时: {end_time - start_time:.2f} 秒\n")
        log.write(f"平均每张: {(end_time - start_time)/(len(all_images) + len(processed_indices_set)):.2f} 秒\n") # 包含已处理的

    # 保存全局结果到JSON文件
    if output_dir:
        result_file = os.path.join(output_dir, f"classification_results_from_jsonl.json")
        try:
            # 添加处理信息到结果中
            enhanced_results = {
                "processing_info": {
                    "jsonl_file": root_folder_path,
                    "total_images": total_original_files,
                    "images_processed": len(all_images) + len(processed_indices_set), # 包含已处理的
                    "processing_time": end_time - start_time,
                },
                "results": all_results
            }
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(enhanced_results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {result_file}")

            # *** 新增：保存错误图片列表 ***
            # 收集所有处理失败的图片
            error_images_list = []
            for result in results_list:
                status = result.get("final_status", "unknown")
                # 定义哪些状态算“错误”。这里排除了成功和不确定（包括标准化失败），只保留真正的错误。
                if status not in ["success", "uncertain", "invalid_category", "format_error"]:
                    error_entry = {
                        "index": result["index"],
                        "image_path": result["image_info"]["full_path"],
                        "relative_path": result["image_info"]["relative_path"],
                        "status": status,
                        "error_message": result["classification_result"].get("error", "Unknown error"),
                        "processed_at": result["processed_at"]
                    }
                    error_images_list.append(error_entry)

            if error_images_list:
                error_log_file = os.path.join(output_dir, f"error_images_list.json")
                try:
                    with open(error_log_file, 'w', encoding='utf-8') as f:
                        json.dump(error_images_list, f, ensure_ascii=False, indent=2)
                    print(f"\n[重要] 发现 {len(error_images_list)} 个错误，详细列表已保存到: {error_log_file}")
                except Exception as e:
                    print(f"保存错误图片列表失败: {str(e)}")
            else:
                print(f"\n[信息] 恭喜！所有图片均处理成功，未生成错误列表文件。")
            # ******************************

            # *** 清理临时文件 ***
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                print(f"[信息] 临时文件 {temp_file_name} 已清理。")
        except Exception as e:
            print(f"保存结果文件失败: {str(e)}")

    # 打印最终统计
    print("\n" + "=" * 60)
    print("图片分类处理完成!")
    print(f"图片总数: {total_original_files}")
    print(f"实际处理数: {len(all_images) + len(processed_indices_set)}") # 包含已处理的
    print(f"并行线程数: {max_workers}")
    print(f"总耗时: {end_time - start_time:.2f} 秒")
    print(f"平均每张: {(end_time - start_time)/(len(all_images) + len(processed_indices_set)):.2f} 秒") # 包含已处理的
    print(f"成功分类: {success_count}")
    print(f"不确定分类: {uncertain_count}")
    print(f"文件未找到: {file_not_found_count}")
    print(f"处理错误: {error_count}")
    print("\n全局各类别统计:")
    print(f"Indoor: {category_counts[1]}")
    print(f"Urban/Built Environment: {category_counts[2]}")
    print(f"Natural Landscape: {category_counts[3]}")
    print(f"No Clear Setting: {category_counts[4]}")
    print(f"Multiple Scenes: {category_counts[5]}")
    print(f"\n详细日志: {log_file}")
    return all_results, subfolder_results

# --- 新增辅助函数用于断点续传和自动保存 ---
def save_partial_results(partial_results, temp_file_path, lock):
    """线程安全地保存部分结果到临时文件"""
    with lock: # 使用传入的锁确保写入安全
        try:
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                json.dump(partial_results, f, ensure_ascii=False, indent=2)
            # print(f"[DEBUG] 部分结果已保存到 {temp_file_path}") # 可选调试信息
        except Exception as e:
            print(f"[警告] 保存部分结果失败: {e}")

def load_partial_results(temp_file_path):
    """加载部分结果"""
    if os.path.exists(temp_file_path):
        try:
            with open(temp_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"[信息] 检测到临时文件，已加载 {len(data.get('results', []))} 条部分结果。")
            return data
        except Exception as e:
            print(f"[警告] 加载临时文件失败: {e}，将重新开始处理。")
    return None

# --- 处理单张图片的函数保持不变 ---
def process_single_image_hierarchical(args):
    """处理来自层次结构的单个图片的包装函数，用于并行处理"""
    image_info, process_index, total_count, system_prompt = args
    thread_safe_print(f"[{process_index}/{total_count}] 开始处理: {image_info['relative_path']} (线程: {threading.current_thread().name})")
    # 检查文件是否存在
    if not os.path.exists(image_info["full_path"]):
        thread_safe_print(f"[{process_index}/{total_count}] ❌ 文件不存在: {image_info['relative_path']}")
        return {
            "index": process_index,
            "image_info": image_info,
            "classification_result": {"error": "文件不存在", "status": "file_not_found"},
            "final_status": "file_not_found",
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    # 分类图片
    result = classify_single_image(image_info["full_path"], system_prompt=system_prompt)
    # 判断结果状态
    status = result.get("status", "unknown")
    if status == "success":
        category = result.get('category', 0)
        category_name = result.get('category_name', '未知')
        confidence = result.get('confidence', '未知')
        thread_safe_print(f"[{process_index}/{total_count}] 成功: {image_info['relative_path']} - {category_name} (置信度: {confidence})")
    elif status in ["uncertain", "invalid_category", "format_error"]:
        category_name = result.get('category_name', '未知')
        confidence = result.get('confidence', '未知')
        thread_safe_print(f"[{process_index}/{total_count}] 不确定: {image_info['relative_path']} - {category_name} (置信度: {confidence})")
    else:
        error_msg = result.get('error', '未知错误')
        thread_safe_print(f"[{process_index}/{total_count}] 错误: {image_info['relative_path']} - {error_msg}")
    # 返回完整结果
    return {
        "index": process_index,
        "image_info": image_info,
        "classification_result": result,
        "final_status": status,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

# --- 修改 main 函数 ---
# --- 修改 main 函数 ---
def main():
    # 让用户输入 JSONL 文件路径
    jsonl_file_path = input("请输入包含图片路径的 JSONL 文件路径: ").strip()
    if not jsonl_file_path:
        print("未指定 JSONL 文件路径，程序退出。")
        return

    # 设置输出目录
    output_dir = "/inspire/hdd/project/embodied-multimodality/public/pywang/hkwang/data_wheel_the_first_task"
    print("API端点: https://gqp5d559gdqdcbqjhedppj9k58qgcepa.openapi-qb.sii.edu.cn")
    print("模型: Qwen2.5-VL-72B-Instruct")
    print("提示词文件: prompt_engine.txt")
    print()
    print(f"输入JSONL文件: {jsonl_file_path}")
    print(f"输出目录: {output_dir}")
    print()

    # --- 预览功能已移除 ---
    # 不再尝试读取整个JSONL文件进行预览，避免大文件导致的性能问题。
    # 程序将直接进入参数配置阶段。
    # ************************

    # 询问其他处理参数
    start_from = input("\n从第几张图片开始? (默认1): ").strip()
    start_from = int(start_from) if start_from.isdigit() else 1
    max_images = input("最多处理多少张? (回车处理全部图片): ").strip()
    max_images = int(max_images) if max_images.isdigit() else None
    max_workers = input("并行线程数? (默认4): ").strip()
    max_workers = int(max_workers) if max_workers.isdigit() and int(max_workers) > 0 else 4
    # *** 新增询问自动保存间隔 ***
    auto_save_interval_input = input("自动保存间隔 (处理多少张后保存一次)? (默认100): ").strip()
    auto_save_interval = int(auto_save_interval_input) if auto_save_interval_input.isdigit() and int(auto_save_interval_input) > 0 else 100
    # ******************************

    print(f"\n最终配置:")
    print(f"  JSONL文件: {jsonl_file_path}")
    print(f"  处理范围: 从第{start_from}张开始, 最多{max_images or '全部'}张")
    print(f"  并行线程: {max_workers}个")
    print(f"  自动保存: 每 {auto_save_interval} 张保存一次")
    # 确认开始
    confirm = input("\n开始处理? (y/n): ").lower().strip()
    if confirm not in ['y', 'yes', '是']:
        print("操作已取消")
        return

    # 开始处理
    print("\n开始图片分类处理...")
    start_time = time.time()
    # *** 传递新的 auto_save_interval 参数 ***
    all_results, subfolder_results = process_images_hierarchical_parallel_sampled(
        root_folder_path=jsonl_file_path, # 传递JSONL路径
        output_dir=output_dir,
        start_from=start_from,
        max_images=max_images,
        max_workers=max_workers,
        auto_save_interval=auto_save_interval
    )
    # **************************************
    end_time = time.time()
    print(f"\n总耗时: {end_time - start_time:.2f} 秒")
    print("图片分类处理完成！")

if __name__ == "__main__":
    main()