"""main selectorのB入力条件を比較する図の手法別スタイル。"""

import paperstyle as ps


METHOD_ORDER = ("B", "B-drop0", "B-drop0-focus", "B-drop0-seed1", "B-2B-drop0")
METHOD_STYLES = ps.method_styles(baselines=METHOD_ORDER)
