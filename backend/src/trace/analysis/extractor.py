"""AST Visitor extracting modules, classes, functions, parameters, decorators, and imports."""

import ast
from dataclasses import dataclass
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    Call,
    CallResolutionStatus,
    Class,
    DecoratorDescriptor,
    EntityKind,
    Function,
    FunctionKind,
    Import,
    ImportKind,
    Module,
    ParameterDescriptor,
    RelationshipKind,
    SourceLocation,
)


@dataclass(frozen=True)
class ExtractedSymbols:
    """Container for all symbols and references extracted from an AST tree."""

    module: Module
    classes: tuple[Class, ...]
    functions: tuple[Function, ...]
    imports: tuple[Import, ...]
    calls: tuple[Call, ...]
    relationships: tuple[AnalysisRelationship, ...]


def derive_module_qualified_name(rel_path: str, source_root: str | None = None) -> tuple[str, bool]:
    """Derive dot-separated module qualified name and package status from a relative path.

    Examples:
        app/main.py -> ("app.main", False)
        app/__init__.py -> ("app", True)
        src/pkg/mod.py (source_root="src") -> ("pkg.mod", False)
    """
    posix_path = Path(rel_path).as_posix()
    if source_root and posix_path.startswith(f"{source_root}/"):
        posix_path = posix_path[len(source_root) + 1 :]

    parts = list(Path(posix_path).parts)
    if not parts:
        return "", False

    file_name = parts[-1]
    is_package = file_name in {"__init__.py", "__init__.pyw"}

    # Strip extension
    stem = Path(file_name).stem
    if is_package:
        module_parts = parts[:-1]
    else:
        module_parts = parts[:-1] + [stem]

    qualified_name = ".".join(module_parts)
    return qualified_name, is_package


class SymbolExtractor:
    """Extracts code intelligence entities and AST relationships from a parsed module."""

    def __init__(
        self,
        internal_packages: set[str] | None = None,
    ) -> None:
        self._internal_packages = internal_packages or set()

    def _format_decorator(self, dec_node: ast.expr) -> DecoratorDescriptor:
        raw_expr = ast.unparse(dec_node)
        line = dec_node.lineno
        args: list[str] = []

        if isinstance(dec_node, ast.Call):
            name = ast.unparse(dec_node.func)
            for arg in dec_node.args:
                args.append(ast.unparse(arg))
            for kw in dec_node.keywords:
                val = ast.unparse(kw.value)
                args.append(f"{kw.arg}={val}" if kw.arg else val)
        else:
            name = raw_expr

        return DecoratorDescriptor(
            name=name,
            raw_expression=raw_expr,
            line_number=line,
            arguments=tuple(args),
        )

    def _extract_parameters(self, args_node: ast.arguments) -> tuple[ParameterDescriptor, ...]:
        params: list[ParameterDescriptor] = []

        # Map defaults to positional args
        defaults = [None] * (len(args_node.args) - len(args_node.defaults)) + list(
            args_node.defaults
        )

        for arg, default in zip(args_node.args, defaults, strict=False):
            annotation_str = ast.unparse(arg.annotation) if arg.annotation else None
            default_str = ast.unparse(default) if default else None
            params.append(
                ParameterDescriptor(
                    name=arg.arg,
                    type_annotation=annotation_str,
                    has_default=default is not None,
                    default_value=default_str,
                )
            )

        # Keyword-only args
        kw_defaults = list(args_node.kw_defaults)
        for arg, default in zip(args_node.kwonlyargs, kw_defaults, strict=False):
            annotation_str = ast.unparse(arg.annotation) if arg.annotation else None
            default_str = ast.unparse(default) if default else None
            params.append(
                ParameterDescriptor(
                    name=arg.arg,
                    type_annotation=annotation_str,
                    has_default=default is not None,
                    default_value=default_str,
                )
            )

        if args_node.vararg:
            params.append(
                ParameterDescriptor(
                    name=f"*{args_node.vararg.arg}",
                    type_annotation=ast.unparse(args_node.vararg.annotation)
                    if args_node.vararg.annotation
                    else None,
                )
            )

        if args_node.kwarg:
            params.append(
                ParameterDescriptor(
                    name=f"**{args_node.kwarg.arg}",
                    type_annotation=ast.unparse(args_node.kwarg.annotation)
                    if args_node.kwarg.annotation
                    else None,
                )
            )

        return tuple(params)

    def extract(
        self,
        tree: ast.AST,
        file_path: str,
        source_root: str | None = None,
        total_lines: int = 1,
    ) -> ExtractedSymbols:
        """Traverse AST and extract all symbols and relationships."""
        module_name, is_package = derive_module_qualified_name(file_path, source_root)
        module_doc = ast.get_docstring(tree) if isinstance(tree, ast.Module) else None
        module_loc = SourceLocation(file_path=file_path, start_line=1, end_line=max(total_lines, 1))

        module_entity = Module(
            qualified_name=module_name,
            file_path=file_path,
            is_package=is_package,
            docstring=module_doc,
            location=module_loc,
        )

        classes: list[Class] = []
        functions: list[Function] = []
        imports: list[Import] = []
        calls: list[Call] = []
        relationships: list[AnalysisRelationship] = []

        # Symbol resolution tables for this file
        imported_symbols: dict[str, str] = {}  # local_name -> qualified_target
        local_functions: set[str] = set()  # function names in this module
        class_methods: dict[str, set[str]] = {}  # class_name -> set of method names

        # Pass 1: Collect imports and module-level declarations
        for node in ast.iter_child_nodes(tree):
            start_l = int(getattr(node, "lineno", 1))
            end_l = int(getattr(node, "end_lineno", start_l) or start_l)
            loc = SourceLocation(
                file_path=file_path,
                start_line=start_l,
                end_line=end_l,
                start_column=getattr(node, "col_offset", None),
                end_column=getattr(node, "end_col_offset", None),
            )

            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp_name = alias.name
                    asname = alias.asname or imp_name
                    top_pkg = imp_name.split(".")[0]
                    is_ext = (
                        top_pkg not in self._internal_packages
                        and top_pkg != module_name.split(".")[0]
                    )

                    imp_entity = Import(
                        source_module=module_name,
                        imported_symbol=imp_name,
                        alias=alias.asname,
                        import_type=ImportKind.IMPORT,
                        is_relative=False,
                        is_external=is_ext,
                        location=loc,
                    )
                    imports.append(imp_entity)
                    imported_symbols[asname] = imp_name

                    relationships.append(
                        AnalysisRelationship(
                            source_type=EntityKind.MODULE,
                            source_identifier=module_name,
                            relationship_type=RelationshipKind.IMPORTS,
                            target_type=EntityKind.MODULE,
                            target_identifier=imp_name,
                            evidence_location=loc,
                        )
                    )

            elif isinstance(node, ast.ImportFrom):
                base_module = node.module or ""
                is_rel = node.level > 0
                if is_rel:
                    # Resolve relative import prefix
                    prefix_parts = module_name.split(".")
                    if is_package:
                        dots = node.level - 1
                    else:
                        dots = node.level
                    target_pkg_parts = prefix_parts[:-dots] if dots > 0 else prefix_parts
                    if base_module:
                        target_pkg_parts.append(base_module)
                    resolved_base = ".".join(target_pkg_parts)
                else:
                    resolved_base = base_module

                top_pkg = resolved_base.split(".")[0] if resolved_base else ""
                is_ext = (
                    top_pkg not in self._internal_packages and top_pkg != module_name.split(".")[0]
                )

                for alias in node.names:
                    sym_name = alias.name
                    asname = alias.asname or sym_name
                    full_target = f"{resolved_base}.{sym_name}" if resolved_base else sym_name

                    imp_entity = Import(
                        source_module=module_name,
                        imported_symbol=full_target,
                        alias=alias.asname,
                        import_type=ImportKind.IMPORT_FROM,
                        is_relative=is_rel,
                        is_external=is_ext,
                        location=loc,
                    )
                    imports.append(imp_entity)
                    imported_symbols[asname] = full_target

                    relationships.append(
                        AnalysisRelationship(
                            source_type=EntityKind.MODULE,
                            source_identifier=module_name,
                            relationship_type=RelationshipKind.IMPORTS,
                            target_type=EntityKind.MODULE,
                            target_identifier=full_target,
                            evidence_location=loc,
                        )
                    )

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                local_functions.add(node.name)

            elif isinstance(node, ast.ClassDef):
                class_methods[node.name] = set()
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                        class_methods[node.name].add(item.name)

        # Pass 2: Extract Classes, Methods, Functions, and Calls
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                class_loc = SourceLocation(
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    start_column=getattr(node, "col_offset", None),
                    end_column=getattr(node, "end_col_offset", None),
                )
                class_qualname = f"{module_name}.{node.name}" if module_name else node.name
                parent_classes = tuple(ast.unparse(base) for base in node.bases)
                decorators = tuple(self._format_decorator(dec) for dec in node.decorator_list)

                cls_entity = Class(
                    name=node.name,
                    qualified_name=class_qualname,
                    module_name=module_name,
                    parent_classes=parent_classes,
                    decorators=decorators,
                    docstring=ast.get_docstring(node),
                    location=class_loc,
                )
                classes.append(cls_entity)

                # Inheritance relationships (EXTENDS)
                for parent_expr in parent_classes:
                    # Resolve parent target if imported
                    parent_target = imported_symbols.get(parent_expr, parent_expr)
                    relationships.append(
                        AnalysisRelationship(
                            source_type=EntityKind.CLASS,
                            source_identifier=class_qualname,
                            relationship_type=RelationshipKind.EXTENDS,
                            target_type=EntityKind.CLASS,
                            target_identifier=parent_target,
                            evidence_location=class_loc,
                        )
                    )

                # Extract Methods inside Class
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                        meth_loc = SourceLocation(
                            file_path=file_path,
                            start_line=item.lineno,
                            end_line=getattr(item, "end_lineno", item.lineno),
                            start_column=getattr(item, "col_offset", None),
                            end_column=getattr(item, "end_col_offset", None),
                        )
                        meth_qualname = f"{class_qualname}.{item.name}"
                        meth_decorators = tuple(
                            self._format_decorator(dec) for dec in item.decorator_list
                        )
                        dec_names = {d.name for d in meth_decorators}

                        if "classmethod" in dec_names:
                            kind = FunctionKind.CLASS_METHOD
                        elif "staticmethod" in dec_names:
                            kind = FunctionKind.STATIC_METHOD
                        elif isinstance(item, ast.AsyncFunctionDef):
                            kind = FunctionKind.ASYNC_METHOD
                        else:
                            kind = FunctionKind.METHOD

                        func_entity = Function(
                            name=item.name,
                            qualified_name=meth_qualname,
                            module_name=module_name,
                            enclosing_class=node.name,
                            kind=kind,
                            parameters=self._extract_parameters(item.args),
                            return_type=ast.unparse(item.returns) if item.returns else None,
                            decorators=meth_decorators,
                            docstring=ast.get_docstring(item),
                            location=meth_loc,
                        )
                        functions.append(func_entity)

                        # Extract call sites inside method
                        self._extract_calls(
                            func_node=item,
                            caller_qualname=meth_qualname,
                            file_path=file_path,
                            current_class=node.name,
                            class_methods=class_methods,
                            local_functions=local_functions,
                            imported_symbols=imported_symbols,
                            module_name=module_name,
                            calls_out=calls,
                            rels_out=relationships,
                        )

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                fn_loc = SourceLocation(
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    start_column=getattr(node, "col_offset", None),
                    end_column=getattr(node, "end_col_offset", None),
                )
                fn_qualname = f"{module_name}.{node.name}" if module_name else node.name
                fn_decorators = tuple(self._format_decorator(dec) for dec in node.decorator_list)
                kind = (
                    FunctionKind.ASYNC_FUNCTION
                    if isinstance(node, ast.AsyncFunctionDef)
                    else FunctionKind.FUNCTION
                )

                func_entity = Function(
                    name=node.name,
                    qualified_name=fn_qualname,
                    module_name=module_name,
                    enclosing_class=None,
                    kind=kind,
                    parameters=self._extract_parameters(node.args),
                    return_type=ast.unparse(node.returns) if node.returns else None,
                    decorators=fn_decorators,
                    docstring=ast.get_docstring(node),
                    location=fn_loc,
                )
                functions.append(func_entity)

                # Extract call sites inside function
                self._extract_calls(
                    func_node=node,
                    caller_qualname=fn_qualname,
                    file_path=file_path,
                    current_class=None,
                    class_methods=class_methods,
                    local_functions=local_functions,
                    imported_symbols=imported_symbols,
                    module_name=module_name,
                    calls_out=calls,
                    rels_out=relationships,
                )

        return ExtractedSymbols(
            module=module_entity,
            classes=tuple(classes),
            functions=tuple(functions),
            imports=tuple(imports),
            calls=tuple(calls),
            relationships=tuple(relationships),
        )

    def _extract_calls(
        self,
        func_node: ast.AST,
        caller_qualname: str,
        file_path: str,
        current_class: str | None,
        class_methods: dict[str, set[str]],
        local_functions: set[str],
        imported_symbols: dict[str, str],
        module_name: str,
        calls_out: list[Call],
        rels_out: list[AnalysisRelationship],
    ) -> None:
        """Find ast.Call nodes within a function and perform static target resolution."""
        for child in ast.walk(func_node):
            if child is func_node or not isinstance(child, ast.Call):
                continue

            call_loc = SourceLocation(
                file_path=file_path,
                start_line=child.lineno,
                end_line=getattr(child, "end_lineno", child.lineno),
                start_column=getattr(child, "col_offset", None),
                end_column=getattr(child, "end_col_offset", None),
            )
            callee_expr = ast.unparse(child.func)
            resolved_target: str | None = None
            status = CallResolutionStatus.UNRESOLVED_DYNAMIC

            # Resolution rule 1: self.method() in class
            if current_class and callee_expr.startswith("self."):
                meth_name = callee_expr[5:]
                if meth_name in class_methods.get(current_class, set()):
                    resolved_target = f"{module_name}.{current_class}.{meth_name}"
                    status = CallResolutionStatus.RESOLVED_INTERNAL
                else:
                    # Inherited or dynamic method
                    status = CallResolutionStatus.UNRESOLVED_DYNAMIC

            # Resolution rule 2: Simple name in local functions
            elif callee_expr in local_functions:
                resolved_target = f"{module_name}.{callee_expr}"
                status = CallResolutionStatus.RESOLVED_INTERNAL

            # Resolution rule 3: Imported symbol
            elif callee_expr in imported_symbols:
                target = imported_symbols[callee_expr]
                resolved_target = target
                top_pkg = target.split(".")[0]
                if top_pkg in self._internal_packages or top_pkg == module_name.split(".")[0]:
                    status = CallResolutionStatus.RESOLVED_INTERNAL
                else:
                    status = CallResolutionStatus.RESOLVED_EXTERNAL

            # Resolution rule 4: Attribute call on imported module, e.g. service.get_items()
            elif "." in callee_expr:
                base_obj = callee_expr.split(".")[0]
                remainder = ".".join(callee_expr.split(".")[1:])
                if base_obj in imported_symbols:
                    target = f"{imported_symbols[base_obj]}.{remainder}"
                    resolved_target = target
                    top_pkg = target.split(".")[0]
                    if top_pkg in self._internal_packages or top_pkg == module_name.split(".")[0]:
                        status = CallResolutionStatus.RESOLVED_INTERNAL
                    else:
                        status = CallResolutionStatus.RESOLVED_EXTERNAL

            call_entity = Call(
                caller_qualified_name=caller_qualname,
                callee_expression=callee_expr,
                resolved_target=resolved_target,
                resolution_status=status,
                location=call_loc,
            )
            calls_out.append(call_entity)

            # CRITICAL CONSTITUTION §I: Only create CALLS edge if target is resolved!
            if (
                status
                in {CallResolutionStatus.RESOLVED_INTERNAL, CallResolutionStatus.RESOLVED_EXTERNAL}
                and resolved_target
            ):
                rels_out.append(
                    AnalysisRelationship(
                        source_type=EntityKind.FUNCTION,
                        source_identifier=caller_qualname,
                        relationship_type=RelationshipKind.CALLS,
                        target_type=EntityKind.FUNCTION,
                        target_identifier=resolved_target,
                        evidence_location=call_loc,
                    )
                )
