# SHACL presentation shapes (working files)

**2026-10-21: `shacl12-presentation-shapes.ttl` moved to `packages/starlayer/starlayer/starontology/shacl12-shacl-ui.ttl`** and is now the registered companion graph `shacl_shacl_ui` (GitHub issue #12). The `.ttl` there is the source; this folder keeps the content notes. Archived 2026-10-17 because nothing read it.

| File | What it is |
|---|---|
| `shacl12-presentation-shapes.ttl` (now `starontology/shacl12-shacl-ui.ttl`) | UI hints for the SHACL vocabulary itself: 18 `sh:PropertyGroup` form sections, `sh:group`/`sh:order` on each predicate, and the `stsh:` form flags (`nodeFormField`, `propertyFormField`, `formMaxCount`, `nodePrimary`). |
| `shacl-presentation-content.md` | The human-editable content the `.ttl` was written from. No generator script exists, so the `.ttl` is the working copy and the two may have drifted. |

It describes the same predicates as `starlayer/shacl/assets/shacl12-validation-shapes.ttl` (the shacl-shacl file): that file says what is valid, this one says how to present it.

## Widgets: standard shui, with `stsh:widgetType` for the rest

Of the 86 widget hints, 66 were converted to standard `shui:editor` (a built-in widget fits) and 20 were left as they were:

| Old `stsh:widgetType` | Now |
|---|---|
| `text` | `shui:TextFieldEditor` |
| `multiline` | `shui:TextAreaEditor` |
| `langstring` | `shui:TextFieldWithLangEditor` |
| `int`, `number` | `shui:NumberFieldEditor` |
| `bool` | `shui:BooleanEditor` |
| `node_kind`, `severity` | `shui:EnumSelectEditor` |
| `datatype`, `class_multi`, `property_multi`, `shape_ref` | `shui:InstancesSelectEditor` |
| `uri_list` | `shui:IRIEditor` |
| `inline_shape` | `shui:DetailsEditor` |

Left as `stsh:widgetType` (no built-in shui widget): `prop_path_expr` (11), `node_expression_list` (3), `node_expression_ref`, `message_list`, `group`, `rdf_term`, `has_value_pick`, `in_list`.

Both are attached the standard way, on a property shape keyed by `sh:path`. They sit in one node shape, `stsh:ShapeEditorShape`, at the end of the `.ttl` (it has no constraints, so it never changes validation):

```turtle
stsh:ShapeEditorShape a sh:NodeShape ;
    sh:targetClass sh:NodeShape, sh:PropertyShape ;
    sh:property [ sh:path sh:order ; shui:editor shui:NumberFieldEditor ] ,
                [ sh:path sh:path  ; stsh:widgetType "prop_path_expr" ] , ... .
```

So "every `sh:order` property shape gets a number field" is one entry. The older (2026-08-15) decision to avoid `shui:editor` is superseded; see the note in `shacl-presentation-content.md`. `sh:group`, `sh:order` and the `stsh:` form flags are still attached to the predicate IRIs, as before.

## Restoring it

Copy the `.ttl` back to `starlayer/shacl/assets/`, re-add `_PRESENTATION_SHAPES_PATH` and its `graph.parse(...)` in `starlayer/shacl/meta_shapes.py`, the `presentation_shapes` entry in `starlayer/shacl/asset_urls.py`, and regenerate the `shacl_meta` snapshot in `starontology`.
