"""Python codemods using LibCST."""

import libcst as cst
from typing import Optional
from .base import BaseCodeMod


class RenameSymbolCodemod(BaseCodeMod):
    """Rename a symbol throughout the code."""

    def __init__(self, old_name: str, new_name: str):
        super().__init__(
            name="rename_symbol",
            description=f"Rename symbol '{old_name}' to '{new_name}'"
        )
        self.old_name = old_name
        self.new_name = new_name

    def preview(self, path: str, text: str) -> str:
        modified = self.apply(path, text)
        return self._create_unified_diff(path, text, modified)

    def apply(self, path: str, text: str) -> str:
        try:
            tree = cst.parse_module(text)
            transformer = RenameSymbolTransformer(self.old_name, self.new_name)
            modified_tree = tree.visit(transformer)
            return modified_tree.code
        except Exception:
            # Fallback: simple string replacement
            return text.replace(self.old_name, self.new_name)


class RenameSymbolTransformer(cst.CSTTransformer):
    """Transformer to rename symbols."""

    def __init__(self, old_name: str, new_name: str):
        self.old_name = old_name
        self.new_name = new_name

    def leave_FunctionDef(self, original_node, updated_node) -> cst.FunctionDef:
        if updated_node.name.value == self.old_name:
            return updated_node.with_changes(name=updated_node.name.with_changes(value=self.new_name))
        return updated_node

    def leave_Name(self, original_node, updated_node) -> cst.Name:
        if updated_node.value == self.old_name:
            return updated_node.with_changes(value=self.new_name)
        return updated_node


class ConvertPrintToLoggingCodemod(BaseCodeMod):
    """Convert print statements to logging calls."""

    def __init__(self, level: str = "info"):
        super().__init__(
            name="convert_print_to_logging",
            description=f"Convert print() calls to logging.{level}()"
        )
        self.level = level.lower()

    def preview(self, path: str, text: str) -> str:
        modified = self.apply(path, text)
        return self._create_unified_diff(path, text, modified)

    def apply(self, path: str, text: str) -> str:
        try:
            tree = cst.parse_module(text)
            transformer = ConvertPrintToLoggingTransformer(self.level)
            modified_tree = tree.visit(transformer)
            return modified_tree.code
        except Exception:
            return text


class ConvertPrintToLoggingTransformer(cst.CSTTransformer):
    """Transformer to convert print to logging."""

    def __init__(self, level: str):
        self.level = level

    def leave_Call(self, original_node, updated_node) -> cst.Call:
        if (isinstance(updated_node.func, cst.Name) and updated_node.func.value == "print"):
            # Convert print(args) to logging.level(args)
            logging_call = cst.Call(
                func=cst.Attribute(
                    value=cst.Name(value="logging"),
                    attr=cst.Name(value=self.level)
                ),
                args=updated_node.args
            )
            return logging_call
        return updated_node


class AddTypeHintsCodemod(BaseCodeMod):
    """Add simple type hints to function parameters."""

    def __init__(self, simple: bool = True):
        super().__init__(
            name="add_type_hints",
            description="Add basic type hints to function parameters"
        )
        self.simple = simple

    def preview(self, path: str, text: str) -> str:
        modified = self.apply(path, text)
        return self._create_unified_diff(path, text, modified)

    def apply(self, path: str, text: str) -> str:
        try:
            tree = cst.parse_module(text)
            transformer = AddTypeHintsTransformer(self.simple)
            modified_tree = tree.visit(transformer)
            return modified_tree.code
        except Exception:
            return text


class AddTypeHintsTransformer(cst.CSTTransformer):
    """Transformer to add simple type hints."""

    def __init__(self, simple: bool):
        self.simple = simple

    def leave_FunctionDef(self, original_node, updated_node) -> cst.FunctionDef:
        if not updated_node.params.params:
            return updated_node

        new_params = []
        for param in updated_node.params.params:
            if param.annotation is None:
                # Add simple type hint based on parameter name
                type_hint = self._infer_type_hint(param.name.value)
                if type_hint:
                    new_param = param.with_changes(
                        annotation=cst.Annotation(
                            annotation=cst.Name(value=type_hint)
                        )
                    )
                    new_params.append(new_param)
                else:
                    new_params.append(param)
            else:
                new_params.append(param)

        new_params_obj = updated_node.params.with_changes(params=new_params)
        return updated_node.with_changes(params=new_params_obj)

    def _infer_type_hint(self, param_name: str) -> Optional[str]:
        """Simple type inference based on naming conventions."""
        if self.simple:
            name_lower = param_name.lower()
            if name_lower in ["count", "index", "length", "size", "num"]:
                return "int"
            elif name_lower in ["name", "text", "message", "content", "data"]:
                return "str"
            elif name_lower in ["flag", "enabled", "disabled", "active"]:
                return "bool"
            elif name_lower in ["items", "values", "args", "params"]:
                return "list"
        return None