"""Top-level package for py_dct_txt."""

__author__ = """???"""
__email__ = "???"

from .py_dct_txt import DctTxt, DctTxtItem, DctTxtStore, add_item, merge_key_dicts

# from .utils import (
#     extract_inline_comments,
#     normalize_to_ascii,
#     split_by_first_sep,
#     yaml_flow_dumps,
#     yaml_flow_loads
# )
#
__all__ = [
    "DctTxt",
    "DctTxtItem",
    "DctTxtStore",
    "add_item",
    "merge_key_dicts",
]
