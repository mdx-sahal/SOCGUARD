# SocGuard — System Diagrams

Generated: April 2026 | Tool: Graphviz 14.1.4

## Files

| # | Diagram | .dot Source | Rendered PNG |
|---|---------|-------------|--------------|
| 1 | System Architecture | `01_architecture.dot` | `01_architecture.png` |
| 2 | Use Case Diagram | `02_use_case.dot` | `02_use_case.png` |
| 3 | ER Diagram | `03_er_diagram.dot` | `03_er_diagram.png` |
| 4 | Data Flow Diagram | `04_data_flow.dot` | `04_data_flow.png` |
| 5 | Class Diagram | `05_class_diagram.dot` | `05_class_diagram.png` |
| 6 | Database Design | `06_database_design.dot` | `06_database_design.png` |

## How to Re-render

```powershell
$dot = "C:\Program Files\Graphviz\bin\dot.exe"
& $dot -Tpng 01_architecture.dot  -o 01_architecture.png  -Gdpi=150
& $dot -Tpng 02_use_case.dot      -o 02_use_case.png      -Gdpi=150
& $dot -Tpng 03_er_diagram.dot    -o 03_er_diagram.png    -Gdpi=150
& $dot -Tpng 04_data_flow.dot     -o 04_data_flow.png     -Gdpi=150
& $dot -Tpng 05_class_diagram.dot -o 05_class_diagram.png -Gdpi=150
& $dot -Tpng 06_database_design.dot -o 06_database_design.png -Gdpi=150
```

## Render as SVG (scalable, better for documents)

```powershell
$dot = "C:\Program Files\Graphviz\bin\dot.exe"
& $dot -Tsvg 01_architecture.dot -o 01_architecture.svg
```

## Online Viewer

Paste any `.dot` file contents at: https://dreampuf.github.io/GraphvizOnline
