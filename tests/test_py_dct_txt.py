#!/usr/bin/env python
"""
完整的 py_dct_txt 测试套件
包含单元测试、集成测试和边界情况测试
"""

import json
import tempfile
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from py_dct_txt.py_dct_txt import DctTxt, DctTxtItem, DctTxtStore
from py_dct_txt.utils import (
    extract_inline_comments,
    normalize_to_ascii,
    split_by_first_sep,
    yaml_flow_dumps,
    yaml_flow_loads,
)


class TestUtils:
    """测试工具函数"""

    def test_extract_inline_comments_basic(self):
        """测试基本行内注释提取"""
        # 正常情况
        comments, code = extract_inline_comments("key := value /* 这是一个注释 */")
        assert comments == ["/* 这是一个注释 */"]
        assert code == "key := value "

        # 多个注释
        comments, code = extract_inline_comments("key /* 注释1 */ := value /* 注释2 */")
        assert len(comments) == 2
        assert "注释1" in comments[0]
        assert "注释2" in comments[1]

        # 无注释
        comments, code = extract_inline_comments("key := value")
        assert comments == []
        assert code == "key := value"

    def test_extract_inline_comments_edge_cases(self):
        """测试行内注释边界情况"""
        # 空字符串
        comments, code = extract_inline_comments("")
        assert comments == [] and code == ""

        # 只有注释
        comments, code = extract_inline_comments("/* 只有注释 */")
        assert comments == ["/* 只有注释 */"] and code == ""

        # 注释在开头
        comments, code = extract_inline_comments("/* 开头注释 */ key := value")
        assert comments == ["/* 开头注释 */"]
        assert "key := value" in code

    def test_split_by_first_sep(self):
        """测试按第一个分隔符分割"""
        import re

        pattern = re.compile(r"(:=|=>|>>|<>)")

        # 正常分隔符
        prefix, sep, suffix = split_by_first_sep(pattern, "key := value")
        assert prefix == "key "
        assert sep == ":="
        assert suffix == " value"

        # 无分隔符
        prefix, sep, suffix = split_by_first_sep(pattern, "key value")
        assert prefix == "key value"
        assert sep == ""
        assert suffix == ""

        # 分隔符在开头
        prefix, sep, suffix = split_by_first_sep(pattern, ":= value")
        assert prefix == ""
        assert sep == ":="
        assert suffix == " value"

        # 分隔符在结尾
        prefix, sep, suffix = split_by_first_sep(pattern, "key :=")
        assert prefix == "key "
        assert sep == ":="
        assert suffix == ""

    def test_yaml_flow_roundtrip(self):
        """测试YAML流格式的序列化和反序列化"""
        test_data = {"name": "test", "value": 123, "items": [1, 2, 3]}

        # 序列化然后反序列化
        yaml_str = yaml_flow_dumps(test_data)
        reconstructed = yaml_flow_loads(yaml_str)

        assert reconstructed == test_data

    def test_yaml_flow_special_values(self):
        """测试YAML特殊值处理"""
        # None值处理
        test_data = {"null_value": None, "list_with_none": [1, None, 3]}
        yaml_str = yaml_flow_dumps(test_data)
        reconstructed = yaml_flow_loads(yaml_str)
        assert reconstructed["null_value"] is None

        # 布尔值
        test_data = {"true_val": True, "false_val": False}
        yaml_str = yaml_flow_dumps(test_data)
        reconstructed = yaml_flow_loads(yaml_str)
        assert reconstructed["true_val"] is True
        assert reconstructed["false_val"] is False

        # 浮点数
        test_data = {"float_val": 3.14, "scientific": 1.23e-4}
        yaml_str = yaml_flow_dumps(test_data)
        reconstructed = yaml_flow_loads(yaml_str)
        assert reconstructed["float_val"] == 3.14

    def test_normalize_to_ascii(self):
        """测试Unicode到ASCII标准化"""
        # 带重音符号的字符
        result = normalize_to_ascii("café")
        assert result == "cafe"

        # 中文字符（应保持不变）
        result = normalize_to_ascii("中文")
        assert result == "中文"

        # 混合字符
        result = normalize_to_ascii("café中文test")
        assert result == "cafe中文test"


class TestDctTxt:
    """测试DctTxt主类"""

    @pytest.fixture
    def dct_txt(self):
        return DctTxt()

    @pytest.fixture
    def sample_data(self):
        """提供示例数据"""
        return [
            "/* 注释1 */ key1 := value1",
            "key2 => value2 /* 行内注释 */",
            "key3 >> [1, 2, 3]",
            "key4 <> name: test, value: 123",
            "",  # 空行
            "   ",  # 空白行
            "key5 := 简单值",
        ]

    @pytest.fixture
    def complex_sample_data(self):
        """提供复杂示例数据"""
        return [
            "/* 多行注释前导 */",
            "key1 := 值1 || 值2 || 值3",
            "/* 行内注释测试 */ key2 => 单值 /* 行内注释1 */ /* 行内注释2 */",
            "key3 >> [1, 2, 3, {nested: value}]",
            "key4 <> name: test, enabled: true, count: 123",
            "key5 := 简单值",
            "/*! 脚本注释 */ script_key",
        ]

    def test_read_as_list_basic(self, dct_txt, sample_data):
        """测试基本列表读取"""
        result = dct_txt.read_as_list(sample_data)

        assert len(result) == 7  # 包含空行和空白行
        assert result[0][1] == "key1"  # 键
        assert result[0][2] == ":="  # 分隔符
        assert "value1" in result[0][3]  # 值

    def test_read_as_list_complex(self, dct_txt, complex_sample_data):
        """测试复杂解析场景"""
        result = dct_txt.read_as_list(complex_sample_data)

        # 检查多值处理
        for item in result:
            if item[1] == "key1":
                assert "||" in item[3]  # 应该包含分隔符

        # 检查脚本注释
        script_items = [item for item in result if item[0].startswith("/*!")]
        assert len(script_items) > 0

    def test_load_dict_basic(self, dct_txt, sample_data):
        """测试基本字典加载"""
        dct_list = dct_txt.read_as_list(sample_data)
        data_dict, globals_dict = dct_txt.load_dict(dct_list)

        assert len(data_dict) > 0
        assert "key1" in data_dict
        assert data_dict["key1"].l == ["value1"]
        assert "key2" in data_dict
        assert data_dict["key2"].s == "value2"

    def test_load_dict_complex(self, dct_txt, complex_sample_data):
        """测试复杂字典加载"""
        dct_list = dct_txt.read_as_list(complex_sample_data)
        data_dict, globals_dict = dct_txt.load_dict(dct_list)

        # 检查多值列表
        key1_item = data_dict.get("key1")
        assert key1_item is not None
        assert len(key1_item.l) == 3

        # 检查嵌套字典
        key4_item = data_dict.get("key4")
        assert key4_item is not None
        assert "name" in key4_item.kvs
        assert key4_item.kvs["name"] == "test"

    def test_roundtrip_basic(self, dct_txt, sample_data):
        """测试基本往返转换"""
        # 读取为字典
        dct_list = dct_txt.read_as_list(sample_data)
        data_dict, _ = dct_txt.load_dict(dct_list)

        # 写回列表格式
        new_list = dct_txt.dump_dict(data_dict)

        # 应该能够成功转换
        assert len(new_list) > 0

        # 重新加载应该得到相同结果
        new_dict, _ = dct_txt.load_dict(new_list)
        assert "key1" in new_dict
        assert new_dict["key1"].l == ["value1"]

    def test_roundtrip_complex(self, dct_txt, complex_sample_data):
        """测试复杂数据往返转换"""
        dct_list = dct_txt.read_as_list(complex_sample_data)
        data_dict, _ = dct_txt.load_dict(dct_list)
        new_list = dct_txt.dump_dict(data_dict)
        new_dict, _ = dct_txt.load_dict(new_list)

        # 验证关键数据完整性
        assert "key1" in new_dict
        assert len(new_dict["key1"].l) == 3
        assert "key4" in new_dict
        assert new_dict["key4"].kvs["name"] == "test"

    def test_save_to_file(self, dct_txt, sample_data, tmp_path):
        """测试保存到文件"""
        dct_list = dct_txt.read_as_list(sample_data)
        data_dict, _ = dct_txt.load_dict(dct_list)

        # 保存到临时文件
        test_file = tmp_path / "test.dct.txt"
        with open(test_file, "w", encoding="utf-8") as f:
            dct_txt.save_dict(data_dict, f)

        assert test_file.exists()
        assert test_file.stat().st_size > 0

        # 验证文件内容可重新加载
        with open(test_file, "r", encoding="utf-8") as f:
            reloaded_dict, _ = dct_txt.read_as_dict(f)
        assert "key1" in reloaded_dict

    def test_error_handling(self, dct_txt):
        """测试错误处理"""
        # 无效YAML格式
        invalid_data = ["key >> [1, 2, 3"]  # 缺少闭合括号
        result = dct_txt.read_as_list(invalid_data)
        # 应该能够优雅处理，而不是崩溃

        # 无效字典格式
        invalid_dict = ["key <> {invalid: json, missing: quote}"]
        result = dct_txt.read_as_list(invalid_dict)
        data_dict, _ = dct_txt.load_dict(result)
        # 应该能够处理解析错误

    def test_batch_processing(self, dct_txt):
        """测试批量处理"""
        # 生成大量测试数据
        large_data = [f"key_{i} := value_{i}" for i in range(100)]
        large_data.extend([f"batch_key => batch_value_{i}" for i in range(50)])

        dct_list = dct_txt.read_as_list(large_data)
        data_dict, _ = dct_txt.load_dict(dct_list)

        # 测试分批处理
        batches = list(dct_txt.get_list_batch(dct_list, batch_size=30, max_extra=5))

        assert len(batches) >= 2  # 应该至少分成2批
        total_items = sum(len(batch) for batch in batches)
        assert total_items == len(dct_list)  # 应该保持总数不变

    def test_format_list_item(self, dct_txt):
        """测试列表项格式化"""
        test_item = (
            "/* 原始注释 */",
            "key",
            ":=",
            "value",
            ["/* 注释1 */", "/* 注释2 */"],
        )
        formatted = dct_txt.format_list_item(test_item)

        assert formatted[0].startswith("/* ")
        assert formatted[0].endswith(" */")
        assert len(formatted[4]) == 2  # 注释应该被正确格式化

    @pytest.mark.parametrize(
        "input_line,expected_key,expected_sep",
        [
            ("key := value", "key", ":="),
            ("key => value", "key", "=>"),
            ("key >> value", "key", ">>"),
            ("key <> value", "key", "<>"),
            ("/* 注释 */ key := value", "key", ":="),
        ],
    )
    def test_separator_parsing_parametrized(
        self, dct_txt, input_line, expected_key, expected_sep
    ):
        """参数化测试：测试不同分隔符的解析"""
        result = dct_txt.read_as_list([input_line])

        assert len(result) == 1
        assert result[0][1] == expected_key
        assert result[0][2] == expected_sep


class TestDctTxtStore:
    """测试DctTxtStore类"""

    @pytest.fixture
    def store(self):
        return DctTxtStore()

    @pytest.fixture
    def sample_files_structure(self, tmp_path):
        """创建示例文件结构"""
        # 创建多个分组文件
        groups = {
            "group1": ["key1 := value1", "key2 => value2"],
            "group2": ["key1 := different_value", "key3 >> [1,2,3]"],
            "group3": ["key4 <> {test: true}"],
        }

        for group_name, lines in groups.items():
            group_file = tmp_path / f"{group_name}.dct.txt"
            group_file.write_text("\n".join(lines), encoding="utf-8")

        return tmp_path

    def test_extract_groupname(self):
        """测试提取组名"""
        # 正常文件名
        assert DctTxtStore.extract_groupname("group1.dct.txt") == "group1"
        assert DctTxtStore.extract_groupname("group1__123.dct.txt") == "group1"
        assert DctTxtStore.extract_groupname("test_group.dct.txt") == "test_group"

        # 异常文件名
        assert DctTxtStore.extract_groupname("invalid.txt") == "unknown"
        assert DctTxtStore.extract_groupname("no_extension") == "unknown"

    def test_create_index_map_basic(self, store):
        """测试基本索引映射创建"""
        keys = ["apple", "banana", "cherry", "123number", "中文", "test"]
        index_map = store.create_index_map(keys)

        # 少的时候不创建索引
        assert "" in index_map
        assert len(index_map) == 1

        many_keys = [f"a{i}" for i in range(1000)]
        index_map = store.create_index_map(keys + many_keys)

        assert "a" in index_map
        assert len(index_map["a"]) == 1001
        assert "b" in index_map
        assert "c" in index_map
        assert "#" in index_map  # 数字和中文应该归到#类别
        assert len(index_map["#"]) == 2
        assert "t" in index_map

    def test_create_index_map_large(self, store):
        """测试大量键的索引映射"""
        # 生成大量测试键
        test_keys = [f"key_{i}" for i in range(2000)]
        test_keys.extend([f"apple_{i}" for i in range(500)])
        test_keys.extend(["123start", "测试", "étagère"])

        index_map = store.create_index_map(test_keys)

        # 验证分类
        assert "k" in index_map
        assert "a" in index_map
        assert "#" in index_map

        # 验证总数
        total_keys = sum(len(keys) for keys in index_map.values())
        assert total_keys == len(test_keys)

    def test_transpose_dict(self):
        """测试字典转置"""
        nested_dict = {
            "group1": {"key1": "value1", "key2": "value2"},
            "group2": {"key1": "value3", "key3": "value4"},
        }

        # 创建模拟的DctTxtItem对象
        item1 = DctTxtItem(k="key1", s="value1")
        item2 = DctTxtItem(k="key2", s="value2")
        item3 = DctTxtItem(k="key1", s="value3")
        item4 = DctTxtItem(k="key3", s="value4")

        nested_dict_with_items = {
            "group1": {"key1": item1, "key2": item2},
            "group2": {"key1": item3, "key3": item4},
        }

        transposed = DctTxtStore.transpose_dict(nested_dict_with_items)

        assert "key1" in transposed
        assert "group1" in transposed["key1"]
        assert "group2" in transposed["key1"]
        assert "key2" in transposed
        assert "key3" in transposed

    def test_load_basic(self, store, sample_files_structure):
        """测试基本文件加载"""
        data = store.load(sample_files_structure)

        assert len(data) > 0
        assert "key1" in data
        # key1 应该出现在两个分组中
        assert len(data["key1"]) == 2
        assert "group1" in data["key1"] and "group2" in data["key1"]

    def test_load_nonexistent_path(self, store, tmp_path):
        """测试加载不存在的路径"""
        non_existent = tmp_path / "nonexistent"
        data = store.load(non_existent)
        assert data == {}  # 应该返回空字典而不是报错

    def test_load_empty_file(self, store, tmp_path):
        """测试加载空文件"""
        empty_file = tmp_path / "empty.dct.txt"
        empty_file.write_text("", encoding="utf-8")
        data = store.load(empty_file)
        assert data == {}

    def test_save_and_reload(self, store, sample_files_structure, tmp_path):
        """测试保存和重新加载"""
        # 先加载数据
        data = store.load(sample_files_structure)

        # 保存到新位置
        output_dir = tmp_path / "output"
        store.save(data, output_dir)

        # 重新加载保存的数据
        reloaded_data = store.load(output_dir)

        # 验证数据完整性
        assert "key1" in reloaded_data
        assert len(reloaded_data["key1"]) == 2

    def test_file_line_iter(self, tmp_path):
        """测试文件行迭代器"""
        # 创建测试文件
        file1 = tmp_path / "test1.dct.txt"
        file2 = tmp_path / "test2.dct.txt"

        file1.write_text("line1\nline2\n", encoding="utf-8")
        file2.write_text("line3\nline4\n", encoding="utf-8")

        lines = list(DctTxtStore.file_line_iter([file1, file2]))
        assert len(lines) == 4
        assert "line1" in lines[0]
        assert "line3" in lines[2]

    def test_clean_empty_folder(self, tmp_path):
        """测试清理空文件夹"""
        # 创建嵌套的空文件夹
        empty_dir = tmp_path / "empty" / "nested"
        empty_dir.mkdir(parents=True)

        # 验证文件夹存在
        assert empty_dir.exists()

        # 清理空文件夹
        DctTxtStore.clean_empty_folder(tmp_path)

        # 空文件夹应该被删除
        assert not empty_dir.exists()
        # 但根目录应该仍然存在
        assert tmp_path.exists()


class TestIntegration:
    """集成测试"""

    def test_end_to_end_basic(self, tmp_path):
        """基本端到端测试"""
        # 创建测试文件
        test_file = tmp_path / "test_group.dct.txt"
        test_content = """/* 测试数据 */ test_key := 测试值
another_key => 另一个值 /* 注释 */
list_key >> [1, 2, 3]
dict_key <> name: test, value: 123
"""
        test_file.write_text(test_content, encoding="utf-8")

        # 加载数据
        store = DctTxtStore()
        data = store.load(tmp_path)

        assert len(data) > 0
        assert "test_key" in data
        assert "another_key" in data
        assert "list_key" in data
        assert "dict_key" in data

        # 保存数据
        output_dir: Path = tmp_path / "output"
        store.save(data, output_dir)

        # 检查输出文件
        # 没有 index (数量 < 1000)
        assert (output_dir / "test_group.dct.txt").exists()

        # 重新加载验证
        reloaded_data = store.load(output_dir)
        assert "test_key" in reloaded_data

    def test_end_to_end_large_data(self, tmp_path):
        """大数据量端到端测试"""
        # 创建大量测试数据
        test_content = []
        for i in range(1000):
            test_content.append(f"key_{i} := value_{i}")
            if i % 10 == 0:
                test_content.append(
                    f"/* 注释 {i} */ batch_key_{i // 10} => batch_value_{i // 10}"
                )

        test_file = tmp_path / "large.dct.txt"
        test_file.write_text("\n".join(test_content), encoding="utf-8")

        # 加载和处理
        store = DctTxtStore()
        data = store.load(tmp_path)

        # 保存
        output_dir = tmp_path / "output_large"
        store.save(data, output_dir, batch_size=200)

        # 检查输出文件
        # 有 index (数量 >= 1000)
        assert (output_dir / "b" / "large.dct.txt").exists()
        assert not (output_dir / "b" / "large__1.dct.txt").exists()
        assert (output_dir / "k" / "large__1.dct.txt").exists()

        # 验证
        reloaded_data = store.load(output_dir)
        assert len(reloaded_data) >= 1000  # 至少1000个键

    def test_roundtrip_complex_data(self, tmp_path):
        """复杂数据往返测试"""
        complex_content = """
/* 多行注释
   第二行 */
multi_value_key := 值1 || 值2 || 值3 /* 行内注释 */

nested_key >> [1, 2, {"nested": true, "items": [1, 2, 3]}]

config_key <> name: 测试配置, enabled: true, settings: {timeout: 30, retries: 3}, tags: [重要, 测试]
"""
        test_file = tmp_path / "complex.dct.txt"
        test_file.write_text(complex_content, encoding="utf-8")

        # 往返测试
        store = DctTxtStore()
        dct_txt = DctTxt()

        # 加载原始数据
        original_data = store.load(tmp_path)

        # 保存到新位置
        output_dir = tmp_path / "output_complex"
        store.save(original_data, output_dir)

        # 重新加载
        final_data = store.load(output_dir)

        # 验证关键数据完整性
        assert "multi_value_key" in final_data
        assert "nested_key" in final_data
        assert "config_key" in final_data


class TestPerformance:
    """性能测试"""

    def test_large_file_processing(self, tmp_path):
        """测试大文件处理性能"""
        dct_txt = DctTxt()

        # 生成大文件（1000行）
        large_content = []
        for i in range(1000):
            if i % 5 == 0:
                large_content.append(f"/* 注释 {i} */ key_{i} := value_{i}")
            else:
                large_content.append(f"key_{i} => value_{i}")

        test_file = tmp_path / "large.dct.txt"
        test_file.write_text("\n".join(large_content), encoding="utf-8")

        # 性能测试
        start_time = time.time()

        with open(test_file, "r", encoding="utf-8") as f:
            result = dct_txt.read_as_dict(f)

        end_time = time.time()
        processing_time = end_time - start_time

        # 验证结果
        assert len(result[0]) == 1000
        # 处理时间应该在合理范围内（通常小于1秒）
        assert processing_time < 5.0, f"处理时间过长: {processing_time}秒"

    def test_memory_efficiency(self, tmp_path):
        """测试内存效率"""
        import tracemalloc

        dct_txt = DctTxt()

        # 生成测试数据
        test_data = [f"key_{i} := value_{i}" for i in range(1000)]

        tracemalloc.start()

        # 执行操作
        dct_list = dct_txt.read_as_list(test_data)
        data_dict, _ = dct_txt.load_dict(dct_list)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 峰值内存使用应该在合理范围内
        assert peak < 10 * 1024 * 1024, f"内存使用过高: {peak}字节"  # 小于10MB


class TestErrorScenarios:
    """错误场景测试"""

    @pytest.fixture
    def dct_txt(self):
        return DctTxt()

    def test_malformed_yaml(self, dct_txt):
        """测试格式错误的YAML处理"""
        # 不完整的YAML
        malformed_data = ["test_key >> [1, 2, 3"]  # 缺少闭合括号
        result = dct_txt.read_as_list(malformed_data)
        data_dict, _ = dct_txt.load_dict(result)

        # 应该能够优雅处理而不崩溃
        assert True  # 只要不抛出异常就通过

    def test_malformed_dict(self, dct_txt):
        """测试格式错误的字典处理"""
        # 无效的字典语法
        malformed_data = ["test_key <> {invalid: syntax, missing: quotes}"]
        result = dct_txt.read_as_list(malformed_data)
        data_dict, _ = dct_txt.load_dict(result)

        # 应该能够优雅处理
        assert True

    def test_unicode_handling(self, dct_txt, tmp_path):
        """测试Unicode字符处理"""
        # 包含各种Unicode字符
        unicode_content = """
normal_key := 正常值
emoji_key := 测试🎉表情
chinese_key := 中文测试
special_key := café naïve résumé
"""
        test_file = tmp_path / "unicode.dct.txt"
        test_file.write_text(unicode_content, encoding="utf-8")

        # 应该能够正确处理
        with open(test_file, "r", encoding="utf-8") as f:
            result = dct_txt.read_as_dict(f)

        assert "normal_key" in result[0]
        assert "emoji_key" in result[0]
        assert "chinese_key" in result[0]
        assert "special_key" in result[0]


# 配置驱动的测试用例
TEST_CASES = [
    {
        "name": "basic_key_value",
        "input": ["key := value"],
        "expected_keys": ["key"],
        "expected_separator": ":=",
    },
    {
        "name": "multiple_values",
        "input": ["key := val1 || val2 || val3"],
        "expected_keys": ["key"],
        "expected_values": 3,
    },
    {
        "name": "with_comments",
        "input": ["/* 注释 */ key => value /* 行内注释 */"],
        "expected_keys": ["key"],
        "has_comments": True,
    },
    {
        "name": "yaml_list",
        "input": ["key >> [1, 2, 3]"],
        "expected_keys": ["key"],
        "expected_separator": ">>",
    },
    {
        "name": "yaml_dict",
        "input": ["key <> {name: test}"],
        "expected_keys": ["key"],
        "expected_separator": "<>",
    },
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=lambda tc: tc["name"])
def test_config_driven(test_case):
    """配置驱动的测试"""
    dct_txt = DctTxt()
    result = dct_txt.read_as_list(test_case["input"])
    assert len(result) == len(test_case["input"])

    if "expected_keys" in test_case:
        assert result[0][1] in test_case["expected_keys"]

    if "expected_separator" in test_case:
        assert result[0][2] == test_case["expected_separator"]

    if "expected_values" in test_case:
        data_dict, _ = dct_txt.load_dict(result)
        key = test_case["expected_keys"][0]
        assert len(data_dict[key].l) == test_case["expected_values"]


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "--tb=short"])
