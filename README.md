# py_dct_txt

## dct_txt 格式

`*.dct.txt` 本质是一个 `*.txt` 文本文件,
但有特殊的格式用来记录存储数据,
文件按行依次解析, 每行都是独立的解析的

- 文本列表行 ( :=右侧 `string[]` / `list[str]` )
    ```plain
    <text>:=[<text>['||'<text>]]
    /* 空值 [] */
    ```

- 文本行 ( =>右侧 `string` / `str` )
    ```plain
    <text>=>[<text>]
    /* 空值 "" */
    ```

- 键值对行 ( <>右侧 `object` / `dict` )
    ```plain
    <text>'<>' <kvs> /* <kvs> 是类似 flow yaml,无外层{}行内yaml格式 */
    /* 没有最外层的 {} 花括号, 解析时;先添加上{}, 就可以复用 yaml 库解析*/
    /* 空值 {} */
    /* key: null 可以略写为 key */
    /* e.g. a, b:1 <=> a: null, b:1 */
    ```

- 值行 ( >>右侧 `any` / `Any` )
    ```plain
    <text>'>>'[<value>]
    /* 空值：解析为 null 或 None */
    ```
- script 行 (特殊, `/*!` 必须在行开始, 不接受前面有空白或其他, 其他情况是注释)
    ```plain
    /*! <identifier>['['[<p1>[,<p2>]...]']'][{[<k1>: <v1>[,<k2>: <v2>]...]}] */
    /* <func_name> 是标识符 */
    /* 可以用[]传递位置参数(param), {} 传递命名参数/选项 */
    ```

符号说明:
`<keyword>`: 表示特殊意义占位
`[]`: 表示可选
`[]...`: 表示可选内容模式重复
`|`: 或
`''`/`""`: 包裹特殊字符, 防止歧义

特别的, 上面的 `<text>` 被解释为:
一直匹配所有字符, 可空"", 直到遇到第一个后面的特殊字符/字符组合)
例如:
(后面的特殊字符为:=) tt:ttt=ttt:= 的 `<text>` 是 tt:ttt=ttt

注释说明:
注释格式为 `/*...*/` (inline)
(类似c的注释，但只能在行内结束, 不能跨行，必须以*/结尾，否则不算注释)
注释可以在任何位置, 最推荐的位置是行的末尾或者单独整行

## 解析流程

### *.dct.txt

1. 读取文件内容(按行) ( split by `\n` )
2. 提取当前行所有的内联注释块 ( `/* ... */` ), 并得到去除所有注释后剩下的内容
3. 按符号分割剩下的内容(`:=` `=>` `<>` `>>`), 符号左边视为 k
4. 得到元组: (开头顶格注释, k, sep 分割符, value, 普通注释 list)
5. 按 sep 解析 value
6. 将上述内容构建为 `DctTxtItem`,
   特别的, k 为空: 根据前面行最近的有值k, 自动分配一个 anchor
7. 构建字典, 以 有值看或anchor 作为字典key,
   key 已经存在则尝试合并

> [!NOTE]
> 存储过程相反
> 特别的, 将所有顶格注释单独成行, 普通注释挪到行末
---
> [!IMPORTANT]
> 反序列化时, k 仅使用 DctTxtItem().k, 不使用 anchor 或字典的key

### store

#### load

1. 获取路径 (文件夹里包含的所有) `*.dct.txt`, 并解析
2. 以文件名作为 group name, 合并得到 group_dict
3. 转置为 key dict

#### save

1. 按 key 得到 index_path, 拆分大的 key_dict
2. 转置小 key_dict 为 group_dict
3. 以 index_path / group_name 为路径存储每个group_dict
4. 如果 group_dict 还是很大,存储为多个文件
5. 记录信息

## sotre key/group dict

```python
key_dict = {
    # any text before ":=" "=>" "<>" ">>"
    "key": {
        "group": DctTxtItem(),
        # file name group.dct.txt
    },
    # example
    "word 1": {
        # group_name1.dct.txt
        # word 1 := content
        "group_name1": DctTxtItem(),
        "group_name2": DctTxtItem(),
    },
    "word 2": {
        "group_name1": DctTxtItem(),
        "group_name2": DctTxtItem(),
        "group_name3": DctTxtItem(),
    },
}

group_dict = {
    "group": {
        "key": DctTxtItem(),
    }
}
```
