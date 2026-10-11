def test_table_row_checks_column_position_not_only_presence():
    from scripts.eval.audit_full_recipe_parsing import row_preserved
    anchor = {"row_label": "study", "expected_cells": {"1": "9", "2": "1/2/3"}}
    correct = {"kind": "table", "cells": [["study", "9", "1/2/3"]]}
    incorrect = {"kind": "table", "cells": [["study", "", "9 1/2/3"]]}
    assert row_preserved([correct], anchor)
    assert not row_preserved([incorrect], anchor)
    assert not row_preserved([{"kind": "table", "cells": [["study", "19", "1/2/3"]]}], anchor)
    assert not row_preserved([{"kind": "table", "cells": [["age", "+200"]]}], {"row_label": "age", "expected_cells": {"1": "+20"}})
    assert not row_preserved([{"kind": "table", "cells": [["age", "+20 +25"]]}], {"row_label": "age", "expected_cells": {"1": "+20"}})
