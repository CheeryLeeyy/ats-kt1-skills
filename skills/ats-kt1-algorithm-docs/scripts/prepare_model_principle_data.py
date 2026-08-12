#!/usr/bin/env python3
"""Build model-principle JSON by reusing verified test-document input/output data."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FIELD_META = {
    "algorithm_id": ("算法编号", "str", "当前算法的业务编号"),
    "algorithm_name": ("算法名称", "str", "当前算法的最新统一名称"),
    "selected_model_name": ("选用模型名称", "str", "本次推理实际加载的模型名称"),
    "model_name": ("模型名称", "str", "本次运行使用的模型名称"),
    "algorithm": ("算法标识", "str", "结果对应的算法标识"),
    "submission_id": ("提交编号", "str", "当前算法提交的业务编号"),
    "method": ("处理方法", "str", "本次运行采用的通信或感知方法"),
    "scenario": ("测试场景", "str", "本次评估使用的交通场景"),
    "num_frames": ("处理帧数", "int", "本次运行实际处理的帧数量"),
    "snr_dB": ("信噪比", "float", "信道信噪比，单位 dB"),
    "train_snr_dB": ("训练信噪比", "float", "信道编码训练使用的信噪比，单位 dB"),
    "test_snr_dB": ("测试信噪比", "float", "推理评估使用的信噪比，单位 dB"),
    "channel_bandwidth_ratio": ("信道带宽比", "float", "语义特征占用的信道带宽比例"),
    "BLER": ("块误码率", "float", "信道传输的块误码率"),
    "Rc": ("有效码率", "float", "信道编码的有效码率"),
    "repeat_times": ("重复推理次数", "int", "随机信道条件下的重复评估次数"),
    "bps": ("每符号比特数", "int", "每个信道符号承载的比特数量"),
    "block_length": ("信道块长度", "int", "单个信道编码块的长度"),
    "ap30": ("交并比 0.30 平均精度", "float", "交并比阈值为 0.30 时的三维检测平均精度"),
    "ap50": ("交并比 0.50 平均精度", "float", "交并比阈值为 0.50 时的三维检测平均精度"),
    "ap_50": ("交并比 0.50 平均精度", "float", "交并比阈值为 0.50 时的三维检测平均精度"),
    "ap70": ("交并比 0.70 平均精度", "float", "交并比阈值为 0.70 时的三维检测平均精度"),
    "ap_70": ("交并比 0.70 平均精度", "float", "交并比阈值为 0.70 时的三维检测平均精度"),
    "precision": ("查准率序列", "float[]", "各置信度阈值对应的检测查准率"),
    "recall": ("查全率序列", "float[]", "各置信度阈值对应的检测查全率"),
    "status": ("运行状态", "str", "正常完成时为 ok 或 completed"),
    "message": ("状态说明", "str", "运行结果或异常状态的可读说明"),
    "timestamp": ("记录时间", "str", "结果生成或日志写入时间"),
    "version": ("结果版本", "str", "结果结构或算法实现版本标识"),
    "granularity": ("压缩粒度", "str", "元素级或低秩分量级压缩方式"),
    "rule": ("贡献评分规则", "str", "参数或奇异分量的差异感知评分方法"),
    "batch_selection": ("校准样本选择方式", "str", "动态随机或固定顺序校准策略"),
    "settings_recorded_in_log": ("日志配置记录", "dict", "运行日志中保存的任务与聚合配置"),
    "final_task_results": ("逐任务结果", "list[dict]", "各持续学习任务的类别范围和准确率"),
    "task_id": ("任务编号", "int", "持续学习任务的顺序编号"),
    "classes": ("任务类别范围", "list[int]", "当前任务包含的类别编号"),
    "accuracy_percent": ("任务准确率", "float", "当前任务的分类准确率，单位百分比"),
    "cumulative_test_accuracy_percent": ("累计测试准确率", "float", "当前及历史任务的累计测试准确率，单位百分比"),
    "average_accuracy_percent": ("平均准确率", "float", "全部已完成任务的平均准确率，单位百分比"),
    "overall_accuracy": ("总体准确率", "float", "全部累计测试样本的总体准确率"),
    "overall_correct": ("正确样本数", "int", "累计预测正确的样本数量"),
    "overall_total": ("测试样本总数", "int", "累计参与评估的样本数量"),
    "task_results": ("逐任务统计", "list[dict]", "各任务的准确率、正确数和样本总数"),
    "config": ("运行配置", "dict", "生成该结果时使用的训练与聚合参数"),
    "model": ("模型配置", "str", "训练或评估使用的模型标识"),
    "distribution": ("数据分布方式", "str", "客户端数据的划分与非独立同分布设置"),
    "federated_setting": ("联邦拓扑设置", "dict", "客户端、边缘节点和上传周期配置"),
    "tasks_completed": ("已完成任务数", "int", "运行完成的持续学习任务数量"),
    "num_clients": ("客户端数量", "int", "参与联邦训练的客户端总数"),
    "num_edges": ("边缘节点数量", "int", "参与层级聚合的边缘节点总数"),
    "best_acc": ("最佳准确率", "float", "当前任务训练过程中的最佳测试准确率"),
    "accuracy": ("测试准确率", "float", "当前任务或总体测试准确率"),
    "correct": ("正确样本数", "int", "当前任务预测正确的样本数量"),
    "total": ("样本总数", "int", "当前任务参与评估的样本数量"),
    "status_code": ("日志级别", "str", "日志记录的状态或级别"),
    "stage": ("处理阶段", "str", "日志对应的数据读取、训练、聚合或输出阶段"),
    "output_path": ("结果路径", "str", "该阶段生成文件的保存位置"),
    "num_output_files": ("输出文件数量", "int", "本次运行生成的文件总数"),
    "checkpoint_epoch": ("模型轮次", "int", "本次恢复并评估的检查点轮次"),
    "output_dir": ("输出目录", "str", "模型运行结果的保存目录"),
    "output_files": ("主要结果文件", "list[str]", "本次生成的主要文件路径清单"),
    "state_dict": ("模型参数字典", "dict[str, Tensor]", "网络各层名称及对应参数张量"),
    "epoch": ("训练轮次", "int", "检查点对应的训练轮次"),
    "optimizer_state": ("优化器状态", "dict", "恢复训练所需的优化器参数"),
    "shape": ("数组形状", "tuple[int]", "数组各维度的长度"),
    "dtype": ("数据类型", "str", "数组元素的数据类型"),
    "gt": ("三维真值框", "ndarray", "当前帧的三维目标真值框数组"),
    "pcd": ("融合点云", "ndarray", "完成协同融合后的点云或鸟瞰特征数组"),
    "pred": ("三维预测框", "ndarray", "模型输出的三维预测框、类别和置信度"),
    "image_size": ("图像尺寸", "tuple[int]", "鸟瞰可视化图的宽度和高度"),
    "bev_points": ("鸟瞰融合点云", "image layer", "图中绘制的融合点云或特征位置"),
    "gt_boxes": ("真值框图层", "image layer", "图中叠加的三维真值框投影"),
    "pred_boxes": ("预测框图层", "image layer", "图中叠加的三维预测框投影"),
    "file_path": ("文件路径", "str", "模型目录中的文件相对路径"),
    "file_size": ("文件大小", "int", "文件字节数"),
    "scalar_name": ("标量名称", "str", "训练或测试曲线的指标名称"),
    "step": ("记录步数", "int", "标量对应的训练轮次或迭代步"),
    "value": ("标量值", "float", "当前步记录的指标值"),
    "data": ("图像像素矩阵", "uint8[][]", "按样本顺序保存的图像像素数据"),
    "fine_labels": ("细粒度类别标签", "list[int]", "每幅图像对应的 100 类标签编号"),
    "coarse_labels": ("粗粒度类别标签", "list[int]", "每幅图像对应的 20 个超类标签编号"),
    "filenames": ("原始图像文件名", "list[str]", "每幅图像对应的原始文件名"),
    "batch_label": ("数据批次说明", "str", "当前 pickle 数据批次的文字说明"),
    "pixel_data": ("图像像素数据", "uint8[H,W,C]", "图像文件解码后的三通道像素矩阵"),
    "class_id": ("类别编号", "str", "由类别目录或标签映射确定的类别编号"),
    "filename": ("样本文件名", "str", "当前图像或数据样本的文件名"),
    "camera_index": ("相机视角编号", "int", "camera0 至 camera3 对应的视角编号"),
    "frame_id": ("帧编号", "str", "与点云、标注和相机图像对应的帧标识"),
    "width": ("图像宽度", "int", "图像水平方向像素数"),
    "height": ("图像高度", "int", "图像垂直方向像素数"),
    "label_map": ("类别标签映射", "dict[str,str]", "类别编号到类别名称的键值映射"),
    "class_name": ("类别名称", "str", "类别编号对应的可读类别名称"),
    "roi_ratio": ("空间特征保留比例", "float", "空间高价值区域的保留比例"),
    "camera0": ("相机标定信息", "dict", "包含位姿、外参矩阵和内参矩阵等相机字段"),
    "cords": ("车辆与相机位姿", "list[float]", "车辆与相机的平移、旋转和姿态参数"),
    "extrinsic": ("相机外参矩阵", "float[4][4]", "车辆或激光雷达坐标到相机坐标的变换矩阵"),
    "intrinsic": ("相机内参矩阵", "float[3][3]", "焦距、主点等相机成像参数"),
    "ego_speed": ("自车速度", "float", "当前帧自车的行驶速度"),
    "lidar_pose": ("激光雷达位姿", "list[float]", "激光雷达在场景坐标系中的位置和姿态"),
    "vehicles": ("车辆三维目标标注", "list[dict]", "车辆目标的类别、位置、尺寸、朝向和运动状态"),
    "carla_traffic_manager": ("交通管理器配置", "dict", "自动变道、跟车距离等交通流控制参数"),
    "auto_lane_change": ("自动变道开关", "bool", "是否允许仿真车辆自动变道"),
    "global_distance": ("全局跟车距离", "float", "交通主体之间的目标跟车距离"),
    "single_cav_list": ("交通主体与传感器列表", "list[dict]", "场景内车辆及其传感器配置"),
    "current_time": ("场景生成时间", "str", "场景数据生成或记录时间"),
    "dataset": ("数据集名称", "str", "算法训练或评估使用的数据集"),
    "ratio": ("压缩比例", "float", "通信预算下保留的参数或低秩分量比例"),
    "calib_batches": ("校准批次数", "int", "用于差异贡献评估的校准数据批次数"),
    "nclients": ("客户端总数", "int", "联邦学习系统中的客户端数量"),
    "pclients": ("每轮参与客户端数", "int", "单轮联邦训练实际参与的客户端数量"),
    "iters": ("联邦迭代轮数", "int", "本次执行的联邦训练迭代次数"),
    "use_taylor": ("泰勒扩展开关", "bool", "是否启用泰勒近似扩展"),
}

CHINESE_VARIABLES = {
    "图像数": "image_count",
    "图像尺寸": "image_shape",
    "文件大小": "file_size",
    "总大小": "total_size",
    "类别数": "class_count",
    "条目数": "entry_count",
    "图像组": "camera_views",
    "数量": "image_count",
    "分辨率": "resolution",
}

FIELD_LABELS = {
    "image_count": "图像数量",
    "image_shape": "图像尺寸",
    "total_size": "数据总大小",
    "class_count": "类别数量",
    "entry_count": "映射条目数量",
    "camera_views": "相机视角组",
    "resolution": "图像分辨率",
    "dataset": "数据集名称",
    "model": "模型名称",
    "ratio": "压缩比例",
    "calib_batches": "校准批次数",
    "nclients": "客户端总数",
    "pclients": "每轮参与客户端数",
    "iters": "联邦迭代轮数",
    "use_taylor": "泰勒扩展开关",
    "VERSION": "点云格式版本",
    "WIDTH": "点云宽度",
    "HEIGHT": "点云高度",
    "POINTS": "点云点数",
    "DATA": "点云存储方式",
    "camera0": "相机标定信息",
    "cords": "车辆与相机位姿",
    "extrinsic": "相机外参矩阵",
    "intrinsic": "相机内参矩阵",
    "ego_speed": "自车速度",
    "lidar_pose": "激光雷达位姿",
    "vehicles": "车辆三维目标标注",
    "carla_traffic_manager": "交通管理器配置",
    "auto_lane_change": "自动变道开关",
    "global_distance": "全局跟车距离",
    "scenario": "场景主体配置",
    "single_cav_list": "交通主体与传感器列表",
    "current_time": "场景生成时间",
    "fine_label_names": "细粒度类别名称",
    "coarse_label_names": "粗粒度类别名称",
}


def inferred_type(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return "bool"
    if re.fullmatch(r"[-+]?\d+", lowered):
        return "int"
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", lowered):
        return "float"
    return "str"


def field_record(name: str, value: str, description: str = "", type_name: str = "") -> dict:
    name = str(name).strip()
    value = str(value).strip()
    meta = FIELD_META.get(name)
    if meta:
        default_description, default_type, default_content = meta
    else:
        default_description = FIELD_LABELS.get(name, f"{name} 字段")
        default_type = inferred_type(value)
        default_content = "文件中记录的对应变量内容"
    return {
        "name": name,
        "type": type_name or default_type,
        "description": str(description).strip() or default_description,
        "content": value or default_content,
    }


def split_parallel_values(label: str, value: str, description: str) -> list[dict]:
    names = [part.strip() for part in re.split(r"\s*/\s*", label) if part.strip()]
    values = [part.strip() for part in re.split(r"\s*/\s*", value) if part.strip()]
    if len(names) <= 1:
        variable = CHINESE_VARIABLES.get(label, label)
        content = value + (f"；{description}" if description else "")
        return [field_record(variable, content, FIELD_LABELS.get(variable, ""))]
    if len(values) != len(names):
        values = [value] * len(names)
    return [
        field_record(name, current + (f"；{description}" if description else ""), FIELD_LABELS.get(name, ""))
        for name, current in zip(names, values)
    ]


def table_fields(content: dict) -> list[dict]:
    headers = [str(value).strip() for value in content.get("headers", [])]
    rows = content.get("rows") or []
    fields: list[dict] = []
    if len(headers) >= 4 and len(rows) == 1:
        row = [str(value).strip() for value in rows[0]]
        for header, value in zip(headers[:-1], row[:-1]):
            variable = CHINESE_VARIABLES.get(header, CHINESE_VARIABLES.get(value, header))
            fields.append(field_record(variable, value, FIELD_LABELS.get(variable, header)))
        return fields
    for row in rows:
        values = [str(value).strip() for value in row]
        if not values:
            continue
        label = values[0]
        value = values[1] if len(values) > 1 else ""
        description = values[2] if len(values) > 2 else label
        fields.extend(split_parallel_values(label, value, description))
    return fields


def code_fields(content: dict) -> list[dict]:
    source = str(content.get("text", ""))
    lines = [line.rstrip() for line in source.splitlines() if line.strip()]
    if any(line.startswith("FIELDS ") for line in lines):
        field_names = next(line.split()[1:] for line in lines if line.startswith("FIELDS "))
        fields = [
            field_record(
                name,
                {
                    "x": "每个点的横向坐标值",
                    "y": "每个点的纵向坐标值",
                    "z": "每个点的高度坐标值",
                    "rgb": "每个点的颜色编码值",
                }.get(name, "每个点对应的属性值"),
                {"x": "横向坐标", "y": "纵向坐标", "z": "高度坐标", "rgb": "颜色编码"}.get(name, "点云属性"),
                "float32",
            )
            for name in field_names
        ]
        for key in ("VERSION", "WIDTH", "HEIGHT", "POINTS", "DATA"):
            match = next((line for line in lines if line.startswith(key + " ")), "")
            if match:
                value = match.split(" ", 1)[1]
                type_name = "int" if key in {"WIDTH", "HEIGHT", "POINTS"} else "str"
                fields.append(field_record(key, value, FIELD_LABELS.get(key, key), type_name))
        return fields
    fields: list[dict] = []
    major = re.search(r"主要字段[：:]\s*([^\n]+)", source)
    if major:
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", major.group(1)):
            fields.append(field_record(name, "类别名称字符串数组", FIELD_LABELS.get(name, f"{name} 字段"), "list[str]"))
    for line in lines:
        stripped = line.strip()
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)", stripped)
        if not match:
            continue
        name, value = match.groups()
        if any(field["name"] == name for field in fields):
            continue
        fields.append(field_record(name, value, FIELD_LABELS.get(name, f"{name} 字段")))
    json_keys = re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', source)
    for name in json_keys:
        if not any(field["name"] == name for field in fields):
            fields.append(field_record(name, "类别名称字符串", "类别编号对应的名称", "str"))
    if "0 bytes" in source and not fields:
        fields.append(field_record("file_size", "0 bytes", "占位文件大小", "int"))
    return fields


def normalize_explicit_fields(item: dict) -> list[dict]:
    fields = item.get("fields")
    if not isinstance(fields, list):
        return []
    result = []
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("file fields must be objects")
        result.append(field_record(field.get("name", ""), field.get("content", ""), field.get("description", ""), field.get("type", "")))
    return result


def input_fields(item: dict) -> list[dict]:
    explicit = normalize_explicit_fields(item)
    if explicit:
        return explicit
    name = str(item.get("name", "")).lower()
    if name in {"cifar-100-python/train", "cifar-100-python/test"}:
        count = "50000 个训练样本" if name.endswith("/train") else "10000 个测试样本"
        return [
            field_record("data", f"{count}，每项为 32×32 RGB 图像的扁平化像素"),
            field_record("fine_labels", "与图像逐项对应的细粒度类别编号"),
            field_record("coarse_labels", "与图像逐项对应的粗粒度超类编号"),
            field_record("filenames", "与图像逐项对应的原始文件名"),
            field_record("batch_label", "训练批次或测试批次说明"),
        ]
    if name == "cifar-100-python/meta":
        return [
            field_record("fine_label_names", "100 个细粒度类别名称", FIELD_LABELS.get("fine_label_names", ""), "list[str]"),
            field_record("coarse_label_names", "20 个粗粒度类别名称", FIELD_LABELS.get("coarse_label_names", ""), "list[str]"),
        ]
    if "imagenet100/train" in name or "imagenet100/val" in name:
        return [
            field_record("pixel_data", "JPEG 解码后的 RGB 图像像素；训练集约 130000 张、验证集约 5000 张"),
            field_record("class_id", "上一级类别目录名称，共 100 个类别"),
            field_record("filename", "当前 JPEG 图像文件名"),
        ]
    if name.endswith("labels.json"):
        return [
            field_record("label_map", "100 组 WordNet 类别编号与类别名称映射"),
            field_record("class_id", "例如 n01968897"),
            field_record("class_name", "例如 chambered nautilus 等对应类别名称"),
        ]
    if "camera0-3.png" in name:
        count = "1424 张" if "test_dataset/" not in name else "924 张"
        return [
            field_record("pixel_data", f"800×600 RGB 图像像素，默认输入共 {count}"),
            field_record("width", "800"),
            field_record("height", "600"),
            field_record("camera_index", "0、1、2、3"),
            field_record("frame_id", "与同目录 PCD 和 YAML 文件一致的帧号"),
        ]
    content = item.get("content")
    fields: list[dict] = []
    if isinstance(content, dict) and content.get("type") == "table":
        fields = table_fields(content)
    elif isinstance(content, dict) and content.get("type") == "code":
        fields = code_fields(content)
    if not fields:
        fields = [field_record("file_content", item.get("detail", ""), "文件主体内容", str(item.get("format", "data")))]
    return fields


def runtime_defaults(test_data: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for config in test_data.get("runtime_configs", []):
        names = [part.strip() for part in re.split(r"\s*/\s*", str(config.get("name", ""))) if part.strip()]
        values = [part.strip() for part in re.split(r"\s*/\s*", str(config.get("default", ""))) if part.strip()]
        if len(values) != len(names):
            values = [str(config.get("default", ""))] * len(names)
        result.update(zip(names, values))
    return result


def described_variables(description: str) -> list[str]:
    candidates = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", description)
    ignored = {"json", "txt", "log", "npy", "png", "yaml", "PyTorch", "TensorBoard", "BEV", "IoU", "AP", "ok", "results", "pkl", "events", "out", "tfevents"}
    return list(dict.fromkeys(value for value in candidates if value not in ignored))


def output_fields(item: dict, test_data: dict) -> list[dict]:
    explicit = normalize_explicit_fields(item)
    if explicit:
        return explicit
    name = str(item.get("name", ""))
    lowered = name.lower()
    description = str(item.get("description", ""))
    defaults = runtime_defaults(test_data)
    for input_item in test_data.get("input_files", []):
        content = input_item.get("content")
        if isinstance(content, dict) and content.get("type") == "table":
            for row in content.get("rows") or []:
                if len(row) < 2:
                    continue
                names = [part.strip() for part in re.split(r"\s*/\s*", str(row[0])) if part.strip()]
                values = [part.strip() for part in re.split(r"\s*/\s*", str(row[1])) if part.strip()]
                if len(names) == len(values):
                    defaults.update(zip(names, values))
    fields: list[dict] = []
    if "eval_intermediate" in lowered:
        for variable in ("ap30", "ap_50", "ap_70", "precision", "recall"):
            fields.append(field_record(variable, "运行评估生成的实际值"))
    elif "_gt.npy" in lowered or "_pcd.npy" in lowered or "_pred.npy" in lowered:
        for variable in ("gt", "pcd", "pred", "shape", "dtype"):
            fields.append(field_record(variable, "数组文件中保存的实际值"))
    elif "vis_" in lowered or lowered.endswith(".png"):
        for variable in ("image_size", "bev_points", "gt_boxes", "pred_boxes"):
            fields.append(field_record(variable, "可视化图中保存的实际内容"))
    elif "_model_dir_" in lowered:
        fields = [field_record("file_path", "模型目录中的相对路径"), field_record("file_size", "对应文件的字节数")]
    elif ".pth" in lowered or "checkpoint" in lowered or "_model.pkl" in lowered:
        fields = [field_record("state_dict", "各网络层的参数张量"), field_record("epoch", "对应任务或训练轮次"), field_record("optimizer_state", "存在时保存优化器状态")]
        if "model_task" in lowered:
            fields.append(field_record("task_id", "文件名中的任务编号"))
    elif "results.pkl" in lowered or "tfevents" in lowered:
        fields = [field_record("config", "持续学习与联邦聚合配置"), field_record("task_results", "逐任务准确率序列"), field_record("scalar_name", "训练或测试指标名称"), field_record("step", "训练轮次或迭代步"), field_record("value", "该步记录的指标值")]
    elif lowered.endswith(".log") or "log_task" in lowered:
        fields = [field_record("timestamp", "日志写入时间"), field_record("stage", "数据读取、训练、聚合、评估或输出阶段"), field_record("message", "该阶段的状态和结果说明")]
        for variable in ("task_id", "accuracy", "best_acc", "output_path"):
            if variable in description or (variable == "accuracy" and "准确率" in description):
                fields.append(field_record(variable, "日志中记录的实际值"))
    elif lowered.endswith(".txt") and "final_results" in lowered:
        fields = [field_record("task_id", "逐任务编号"), field_record("classes", "各任务类别范围"), field_record("accuracy_percent", "逐任务准确率"), field_record("average_accuracy_percent", "全部任务平均准确率")]
    if "run_summary.json" in lowered:
        fields = [field_record("status", "completed"), field_record("num_output_files", "本次输出目录实际文件数"), field_record("checkpoint_epoch", defaults.get("checkpoint epoch", "模型实际恢复轮次")), field_record("output_dir", "/app/data/output"), field_record("output_files", "主要评估、数组和可视化文件清单")]
    structured_description = ".json" in lowered or ".yaml" in lowered
    for variable in described_variables(description) if structured_description else []:
        if any(field["name"] == variable for field in fields):
            continue
        content = defaults.get(variable, "运行后写入的实际值")
        if variable == "algorithm_id":
            content = str(test_data.get("algorithm_id", ""))
        elif variable in {"algorithm_name", "selected_model_name", "model_name"}:
            content = str(test_data.get("algorithm_name", ""))
        elif variable == "num_frames":
            content = defaults.get("max_frames", content)
        elif variable == "status" and "status 预期为 ok" in description:
            content = "ok"
        fields.append(field_record(variable, content))
    if lowered.endswith("result.json"):
        for variable in ("snr_dB", "train_snr_dB", "test_snr_dB", "channel_bandwidth_ratio", "repeat_times", "bps", "block_length"):
            if variable in defaults and not any(field["name"] == variable for field in fields):
                fields.append(field_record(variable, defaults[variable]))
        if "ROI ratio" in defaults and not any(field["name"] == "roi_ratio" for field in fields):
            fields.append(field_record("roi_ratio", defaults["ROI ratio"]))
        if "版本" in description and not any(field["name"] == "version" for field in fields):
            fields.append(field_record("version", "结果文件中记录的版本标识"))
    if not fields:
        fields = [field_record("file_content", description, "文件主体内容", str(item.get("format", "data")))]
    return fields


def output_file_description(item: dict) -> str:
    name = str(item.get("name", ""))
    lowered = name.lower()
    if "run.log" in lowered:
        return "算法运行过程日志"
    if "final_results" in lowered:
        return "最终测试结果摘要"
    if "model_task" in lowered:
        return "分任务模型参数文件"
    if "results.pkl" in lowered or "tfevents" in lowered:
        return "训练结果与事件曲线记录"
    if "log_task" in lowered:
        return "逐任务训练与测试日志"
    if "checkpoint" in lowered:
        return "训练检查点文件"
    if "_model.pkl" in lowered:
        return "增量任务模型参数文件"
    if "eval_intermediate" in lowered:
        return "环境态势认知精度评估文件"
    if "_gt.npy" in lowered or "_pcd.npy" in lowered or "_pred.npy" in lowered:
        return "真值框、融合点云与预测框数组"
    if "vis_" in lowered:
        return "鸟瞰协同感知可视化图"
    if "_model_dir_" in lowered:
        return "模型目录文件清单"
    if "run_summary" in lowered:
        return "运行结果汇总文件"
    if lowered.endswith("result.json"):
        return "结构化算法运行结果"
    return "模型运行输出文件"


def file_item(item: dict, fields: list[dict], *, output: bool = False) -> dict:
    description = output_file_description(item) if output else str(item.get("title") or item.get("description") or "输入数据文件").strip()
    description = re.sub(r"[（(][^（）()]*[）)]", "", description).strip()
    return {
        "name": require_text(item, "name"),
        "file_description": description,
        "format": str(item.get("format", "data")).strip() or "data",
        "fields": fields,
    }


def is_docker_runtime_file(item: dict) -> bool:
    return bool(item.get("runtime_only")) or str(item.get("role", "")).strip().lower() == "docker-runtime"


def require_text(data: dict, key: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def require_semantic_summary(spec: dict, key: str, package: str) -> str:
    """Read a short semantic summary; filenames and variable names belong below it."""
    value = require_text(spec, key)
    if len(value) > 80:
        raise ValueError(f"{package} {key} must be a brief Chinese semantic summary")
    if any(token in value for token in (".json", ".yaml", ".yml", ".npy", ".txt", ".log", ".pth", ".pkl", "/", "<", ">")):
        raise ValueError(f"{package} {key} must not enumerate filenames or paths")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names", required=True, type=Path)
    parser.add_argument("--test-data-dir", required=True, type=Path)
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    names = json.loads(args.names.read_text(encoding="utf-8"))["algorithms"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    test_paths = sorted(
        args.test_data_dir.glob("algo1-4-j-*.json"),
        key=lambda path: int(path.stem.rsplit("-", 1)[1]),
    )
    if not test_paths:
        raise ValueError("no test-document JSON files found")

    for test_path in test_paths:
        test_data = json.loads(test_path.read_text(encoding="utf-8"))
        package = require_text(test_data, "package_name")
        algorithm_id = require_text(test_data, "algorithm_id")
        if algorithm_id not in names:
            raise ValueError(f"latest-name mapping is missing {algorithm_id}")
        current_name = require_text(names[algorithm_id], "current_name")
        if require_text(test_data, "algorithm_name") != current_name:
            raise ValueError(f"{package} test data does not yet use the latest model name")

        spec_path = args.spec_dir / f"{package}.json"
        if not spec_path.is_file():
            raise ValueError(f"model-principle spec is missing: {spec_path}")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        intro = spec.get("intro_paragraphs")
        nodes = spec.get("framework_nodes")
        flow_steps = spec.get("flow_steps")
        if not isinstance(intro, list):
            raise ValueError(f"{package} requires a list of introduction paragraphs")
        intro = [str(value).strip() for value in intro if str(value).strip()]
        if len(intro) < 4:
            raise ValueError(f"{package} requires at least four introduction paragraphs")
        if len("".join(intro)) < 350:
            raise ValueError(f"{package} introduction must contain at least 350 characters")
        if not isinstance(nodes, list) or len(nodes) != 6:
            raise ValueError(f"{package} requires exactly six framework nodes")
        nodes = [str(value).strip() for value in nodes]
        for node in nodes:
            separator = "：" if "：" in node else ":" if ":" in node else ""
            if not separator:
                raise ValueError(f"{package} framework node needs 模块名：作用说明: {node}")
            name, detail = (part.strip() for part in node.split(separator, 1))
            if not name or len(detail) < 6:
                raise ValueError(f"{package} framework node description is too short: {node}")
        if not isinstance(flow_steps, list) or len(flow_steps) != 6:
            raise ValueError(f"{package} requires exactly six detailed flow steps")
        flow_steps = [str(value).strip() for value in flow_steps]
        if any(len(value) < 12 for value in flow_steps):
            raise ValueError(f"{package} flow steps must explain data processing in detail")
        normalized_flow = [
            re.sub(r"^步骤\s*\d+\s*[：:]\s*", "", value).strip() for value in flow_steps
        ]
        if normalized_flow == nodes or set(normalized_flow) == set(nodes):
            raise ValueError(f"{package} flow steps must not duplicate or reorder framework nodes")
        if not any(token in normalized_flow[0] for token in ("输入", "读取", "接收", "加载")):
            raise ValueError(f"{package} first flow step must start from input data")
        if not any(token in normalized_flow[-1] for token in ("输出", "写入", "保存", "生成")):
            raise ValueError(f"{package} last flow step must produce the output data")
        supported_scenarios = names[algorithm_id].get("supported_scenarios")
        if not isinstance(supported_scenarios, list) or not supported_scenarios:
            raise ValueError(f"{package} requires checked collaboration scenes from workbook columns C-F")
        supported_scenarios = [str(value).strip() for value in supported_scenarios if str(value).strip()]
        if not supported_scenarios:
            raise ValueError(f"{package} collaboration-scene list is empty")

        inputs = [
            file_item(item, input_fields(item))
            for item in test_data["input_files"]
            if not is_docker_runtime_file(item)
        ]
        outputs = [
            file_item(item, output_fields(item, test_data), output=True)
            for item in test_data["output_files"]
            if not is_docker_runtime_file(item)
        ]
        if not inputs or not outputs:
            raise ValueError(f"{package} requires non-runtime input and output files")
        result = {
            "algorithm_id": algorithm_id,
            "package_name": package,
            "algorithm_name": current_name,
            "project_name": spec.get("project_name", "自主式交通系统跨域计算与决策优化"),
            "topic_name": spec.get("topic_name", "端边云协同的多方式自主交通系统全域认知计算"),
            "function_description": require_text(spec, "function_description"),
            "input_summary": require_semantic_summary(spec, "input_summary", package),
            "inputs": inputs,
            "output_summary": require_semantic_summary(spec, "output_summary", package),
            "outputs": outputs,
            "service_scene": require_text(spec, "service_scene"),
            "supported_scenarios": supported_scenarios,
            "supported_scenarios_text": "，".join(supported_scenarios),
            "responsible_unit": str(spec.get("responsible_unit", "北京邮电大学")),
            "intro_paragraphs": intro,
            "framework_nodes": nodes,
            "flow_steps": flow_steps,
        }
        output = args.output_dir / f"{package}.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
