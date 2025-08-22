# src/codegraphcontext/tools/graph_builder.py
import asyncio
import ast
import logging
import os
import importlib
from pathlib import Path
from typing import Any, Coroutine, Dict, Optional, Tuple
from datetime import datetime

from ..core.database import DatabaseManager
from ..core.jobs import JobManager, JobStatus

logger = logging.getLogger(__name__)


def debug_log(message):
    """Write debug message to a file"""
    debug_file = os.path.expanduser("~/mcp_debug.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(debug_file, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()


class CyclomaticComplexityVisitor(ast.NodeVisitor):
    """Calculates cyclomatic complexity for a given AST node."""
    def __init__(self):
        self.complexity = 1

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node):
        self.complexity += len(node.items)
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncWith(self, node):
        self.complexity += len(node.items)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_ListComp(self, node):
        self.complexity += len(node.generators)
        self.generic_visit(node)

    def visit_SetComp(self, node):
        self.complexity += len(node.generators)
        self.generic_visit(node)

    def visit_DictComp(self, node):
        self.complexity += len(node.generators)
        self.generic_visit(node)

    def visit_GeneratorExp(self, node):
        self.complexity += len(node.generators)
        self.generic_visit(node)

    def visit_IfExp(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_match_case(self, node):
        self.complexity += 1
        self.generic_visit(node)


class CodeVisitor(ast.NodeVisitor):
    """Enhanced AST visitor to extract code elements with better function call detection"""

    def __init__(self, file_path: str, is_dependency: bool = False):
        self.file_path = file_path
        self.is_dependency = is_dependency
        self.functions = []
        self.classes = []
        self.variables = []
        self.imports = []
        self.function_calls = []
        self.current_context = None
        self.current_class = None
        self.context_stack = []

    def _push_context(self, name: str, node_type: str, line_number: int):
        """Push a new context onto the stack"""
        self.context_stack.append(
            {
                "name": name,
                "type": node_type,
                "line_number": line_number,
                "previous_context": self.current_context,
                "previous_class": self.current_class,
            }
        )
        self.current_context = name
        if node_type == "class":
            self.current_class = name

    def _pop_context(self):
        """Pop the current context from the stack"""
        if self.context_stack:
            prev_context = self.context_stack.pop()
            self.current_context = prev_context["previous_context"]
            self.current_class = prev_context["previous_class"]

    def visit_FunctionDef(self, node):
        """Visit function definitions"""
        complexity_visitor = CyclomaticComplexityVisitor()
        complexity_visitor.visit(node)
        # Capture function parameters with their type annotations as variables
        for arg in node.args.args:
            # Check if the parameter has a type annotation
            if arg.annotation:
                var_data = {
                    "name": arg.arg,
                    "line_number": node.lineno,
                    "value": ast.unparse(arg.annotation) if hasattr(ast, "unparse") else "",
                    "context": node.name,
                    "class_context": self.current_class,
                    "is_dependency": self.is_dependency,
                    "parent_line": node.lineno,
                }
                self.variables.append(var_data)
        func_data = {
            "name": node.name,
            "line_number": node.lineno,
            "end_line": node.end_lineno if hasattr(node, "end_lineno") else None,
            "args": [arg.arg for arg in node.args.args],
            "source": ast.unparse(node) if hasattr(ast, "unparse") else "",
            "context": self.current_context,
            "class_context": self.current_class,
            "is_dependency": self.is_dependency,
            "docstring": ast.get_docstring(node),
            "decorators": [
                ast.unparse(dec) if hasattr(ast, "unparse") else ""
                for dec in node.decorator_list
            ],
            "cyclomatic_complexity": complexity_visitor.complexity,
        }
        self.functions.append(func_data)
        self._push_context(node.name, "function", node.lineno)
        self.generic_visit(node)
        self._pop_context()

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definitions"""
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        """Visit class definitions"""
        class_data = {
            "name": node.name,
            "line_number": node.lineno,
            "end_line": node.end_lineno if hasattr(node, "end_lineno") else None,
            "bases": [
                ast.unparse(base) if hasattr(ast, "unparse") else ""
                for base in node.bases
            ],
            "source": ast.unparse(node) if hasattr(ast, "unparse") else "",
            "context": self.current_context,
            "is_dependency": self.is_dependency,
            "docstring": ast.get_docstring(node),
            "decorators": [
                ast.unparse(dec) if hasattr(ast, "unparse") else ""
                for dec in node.decorator_list
            ],
        }
        self.classes.append(class_data)
        self._push_context(node.name, "class", node.lineno)
        self.generic_visit(node)
        self._pop_context()

    def visit_Assign(self, node):
        """Visit variable assignments"""
        parent_line = None
        if self.context_stack:
            parent_line = self.context_stack[-1].get("line_number")

        for target in node.targets:
            if isinstance(target, ast.Name):
                var_data = {
                    "name": target.id,
                    "line_number": node.lineno,
                    "value": ast.unparse(node.value) if hasattr(ast, "unparse") else "",
                    "context": self.current_context,
                    "class_context": self.current_class,
                    "is_dependency": self.is_dependency,
                    "parent_line": parent_line,
                }
                self.variables.append(var_data)
            elif isinstance(target, ast.Attribute):
                var_data = {
                    "name": target.attr,
                    "line_number": node.lineno,
                    "value": ast.unparse(node.value) if hasattr(ast, "unparse") else "",
                    "context": self.current_context,
                    "class_context": self.current_class,
                    "is_dependency": self.is_dependency,
                    "parent_line": parent_line,
                }
                self.variables.append(var_data)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        """Visit annotated assignments (type hints)"""
        if isinstance(node.target, ast.Name):
            var_data = {
                "name": node.target.id,
                "line_number": node.lineno,
                "value": (
                    ast.unparse(node.value)
                    if node.value and hasattr(ast, "unparse")
                    else ""
                ),
                "context": self.current_context,
                "class_context": self.current_class,
                "is_dependency": self.is_dependency,
            }
            self.variables.append(var_data)
        self.generic_visit(node)

    def visit_Import(self, node):
        """Visit import statements"""
        for name in node.names:
            import_data = {
                "name": name.name,
                "line_number": node.lineno,
                "alias": name.asname,
                "context": self.current_context,
                "is_dependency": self.is_dependency,
            }
            self.imports.append(import_data)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """
        Visit from-import statements, now correctly capturing the relative path.
        """
        # Create the relative path prefix (e.g., '.', '..') based on the level.
        prefix = '.' * node.level

        for alias in node.names:
            # If node.module is None, it's an import like `from . import name`
            if node.module:
                full_name = f"{prefix}{node.module}.{alias.name}"
            else:
                # The full name is just the prefix and the imported name
                full_name = f"{prefix}{alias.name}"

            import_data = {
                "name": full_name,
                "line_number": node.lineno,
                "alias": alias.asname,
                "context": self.current_context,
                "is_dependency": self.is_dependency,
            }
            self.imports.append(import_data)

    def visit_Call(self, node):
        """Visit function calls with enhanced detection"""
        call_name = None
        full_call_name = None
        try:
            call_args = [
                ast.unparse(arg) if hasattr(ast, "unparse") else "" for arg in node.args
            ]
        except:
            call_args = []

        if isinstance(node.func, ast.Name):
            call_name = node.func.id
            full_call_name = call_name
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
            try:
                full_call_name = ast.unparse(node.func)
            except:
                full_call_name = call_name

        if call_name and call_name not in __builtins__:
            call_data = {
                "name": call_name,
                "full_name": full_call_name,
                "line_number": node.lineno,
                "args": call_args,
                "context": self.current_context,
                "class_context": self.current_class,
                "is_dependency": self.is_dependency,
            }
            self.function_calls.append(call_data)
        self.generic_visit(node)


class GraphBuilder:
    """Module for building and managing the Neo4j code graph."""

    def __init__(self, db_manager: DatabaseManager, job_manager: JobManager, loop: asyncio.AbstractEventLoop):
        self.db_manager = db_manager
        self.job_manager = job_manager
        self.loop = loop  # Store the main event loop
        self.driver = self.db_manager.get_driver()
        self.create_schema()

    def create_schema(self):
        """Create constraints and indexes in Neo4j."""
        with self.driver.session() as session:
            try:
                session.run("CREATE CONSTRAINT repository_path IF NOT EXISTS FOR (r:Repository) REQUIRE r.path IS UNIQUE")
                session.run("CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE")
                session.run("CREATE CONSTRAINT directory_path IF NOT EXISTS FOR (d:Directory) REQUIRE d.path IS UNIQUE")
                session.run("CREATE CONSTRAINT function_unique IF NOT EXISTS FOR (f:Function) REQUIRE (f.name, f.file_path, f.line_number) IS UNIQUE")
                session.run("CREATE CONSTRAINT class_unique IF NOT EXISTS FOR (c:Class) REQUIRE (c.name, c.file_path, c.line_number) IS UNIQUE")
                session.run("CREATE CONSTRAINT variable_unique IF NOT EXISTS FOR (v:Variable) REQUIRE (v.name, v.file_path, v.line_number) IS UNIQUE")
                session.run("CREATE CONSTRAINT module_name IF NOT EXISTS FOR (m:Module) REQUIRE m.name IS UNIQUE")
                
                # Create a full-text search index for code search
                session.run("""
                    CREATE FULLTEXT INDEX code_search_index IF NOT EXISTS 
                    FOR (n:Function|Class|Variable) 
                    ON EACH [n.name, n.source, n.docstring]
                """)
                
                logger.info("Database schema verified/created successfully")
            except Exception as e:
                logger.warning(f"Schema creation warning: {e}")

    def add_repository_to_graph(self, repo_path: Path, is_dependency: bool = False):
        """Adds a repository node using its absolute path as the unique key."""
        repo_name = repo_path.name
        repo_path_str = str(repo_path.resolve())
        with self.driver.session() as session:
            session.run(
                """
                MERGE (r:Repository {path: $path})
                SET r.name = $name, r.is_dependency = $is_dependency
                """,
                path=repo_path_str,
                name=repo_name,
                is_dependency=is_dependency,
            )

    def add_file_to_graph(self, file_data: Dict, repo_name: str):
        """Adds a file and its contents within a single, unified session."""
        file_path_str = str(Path(file_data['file_path']).resolve())
        file_name = Path(file_path_str).name
        is_dependency = file_data.get('is_dependency', False)

        with self.driver.session() as session:
            try:
                repo_result = session.run("MATCH (r:Repository {name: $repo_name}) RETURN r.path as path", repo_name=repo_name).single()
                relative_path = str(Path(file_path_str).relative_to(Path(repo_result['path']))) if repo_result else file_name
            except ValueError:
                relative_path = file_name

            # Create/Merge the file node
            session.run("""
                MERGE (f:File {path: $path})
                SET f.name = $name, f.relative_path = $relative_path, f.is_dependency = $is_dependency
            """, path=file_path_str, name=file_name, relative_path=relative_path, is_dependency=is_dependency)

            # Create directory structure and link it
            file_path_obj = Path(file_path_str)
            repo_path_obj = Path(repo_result['path'])
            
            relative_path_to_file = file_path_obj.relative_to(repo_path_obj)
            
            parent_path = str(repo_path_obj)
            parent_label = 'Repository'

            # Create nodes for each directory part of the path
            for part in relative_path_to_file.parts[:-1]: # For each directory in the path
                current_path = Path(parent_path) / part
                current_path_str = str(current_path)
                
                session.run(f"""
                    MATCH (p:{parent_label} {{path: $parent_path}})
                    MERGE (d:Directory {{path: $current_path}})
                    SET d.name = $part
                    MERGE (p)-[:CONTAINS]->(d)
                """, parent_path=parent_path, current_path=current_path_str, part=part)

                parent_path = current_path_str
                parent_label = 'Directory'

            # Link the last directory/repository to the file
            session.run(f"""
                MATCH (p:{parent_label} {{path: $parent_path}})
                MATCH (f:File {{path: $file_path}})
                MERGE (p)-[:CONTAINS]->(f)
            """, parent_path=parent_path, file_path=file_path_str)

            for item_data, label in [(file_data['functions'], 'Function'), (file_data['classes'], 'Class'), (file_data['variables'], 'Variable')]:
                for item in item_data:
                    query = f"""
                        MATCH (f:File {{path: $file_path}})
                        MERGE (n:{label} {{name: $name, file_path: $file_path, line_number: $line_number}})
                        SET n += $props
                        MERGE (f)-[:CONTAINS]->(n)
                    """
                    session.run(query, file_path=file_path_str, name=item['name'], line_number=item['line_number'], props=item)

            for imp in file_data['imports']:
                session.run("""
                    MATCH (f:File {path: $file_path})
                    MERGE (m:Module {name: $name})
                    SET m.alias = $alias
                    MERGE (f)-[:IMPORTS]->(m)
                """, file_path=file_path_str, **imp)

            for class_item in file_data.get('classes', []):
                if class_item.get('bases'):
                    for base_class_name in class_item['bases']:
                        session.run("""
                            MATCH (child:Class {name: $child_name, file_path: $file_path})
                            MATCH (parent:Class {name: $parent_name})
                            MERGE (child)-[:INHERITS_FROM]->(parent)
                        """, 
                        child_name=class_item['name'], 
                        file_path=file_path_str, 
                        parent_name=base_class_name)

            self._create_class_method_relationships(session, file_data)
            self._create_contextual_relationships(session, file_data)
    
    def _create_contextual_relationships(self, session, file_data: Dict):
        """Create CONTAINS relationships from functions/classes to their children."""
        file_path = str(Path(file_data['file_path']).resolve())
        
        for func in file_data.get('functions', []):
            if func.get('class_context'):
                session.run("""
                    MATCH (c:Class {name: $class_name, file_path: $file_path})
                    MATCH (fn:Function {name: $func_name, file_path: $file_path, line_number: $func_line})
                    MERGE (c)-[:CONTAINS]->(fn)
                """, 
                class_name=func['class_context'],
                file_path=file_path,
                func_name=func['name'],
                func_line=func['line_number'])

        for var in file_data.get('variables', []):
            context = var.get('context')
            parent_line = var.get('parent_line')
            
            if context and parent_line:
                parent_label = "Function"
                parent_node_data = None
                
                for class_data in file_data.get('classes', []):
                    if class_data['name'] == context and class_data['line_number'] == parent_line:
                        parent_label = "Class"
                        parent_node_data = class_data
                        break
                
                if not parent_node_data:
                    for func_data in file_data.get('functions', []):
                        if func_data['name'] == context and func_data['line_number'] == parent_line:
                            parent_label = "Function"
                            parent_node_data = func_data
                            break
                
                if parent_node_data:
                    session.run(f"""
                        MATCH (p:{parent_label} {{name: $parent_name, file_path: $file_path, line_number: $parent_line}})
                        MATCH (v:Variable {{name: $var_name, file_path: $file_path, line_number: $var_line}})
                        MERGE (p)-[:CONTAINS]->(v)
                    """,
                    parent_name=context,
                    file_path=file_path,
                    parent_line=parent_line,
                    var_name=var['name'],
                    var_line=var['line_number'])
            else:
                session.run("""
                    MATCH (f:File {path: $file_path})
                    MATCH (v:Variable {name: $var_name, file_path: $file_path, line_number: $var_line})
                    MERGE (f)-[:CONTAINS]->(v)
                """,
                file_path=file_path,
                var_name=var['name'],
                var_line=var['line_number'])
    
    def _create_function_calls(self, session, file_data: Dict):
        """Create CALLS relationships between functions based on function_calls data with improved matching"""
        caller_file_path = str(Path(file_data['file_path']).resolve())
        def create_function_call_map(data):
            """
            Processes JSON data to map function calls to their file paths.

            Args:
                data (dict): The parsed JSON data containing function_calls,
                            variables, and imports.

            Returns:
                list: A list of dictionaries, where each dictionary represents a
                    function call and includes its resolved file path.
            """
            function_calls = data.get("function_calls", [])
            variables = data.get("variables", [])
            imports = data.get("imports", [])
            current_file_path = data.get("file_path", "unknown_file.py")
            # Create quick lookup dictionaries for variables and imports for efficiency
            variable_to_class = {
                var["name"]: var["value"].split("(")[0] for var in variables
            }

            class_to_path = {}
            for imp in imports:
                imp_name = imp["name"]
                levels = len(imp_name) - len(imp_name.lstrip('.'))  # count dots
                parts = imp_name.lstrip('.').split(".")
                class_name = parts[-1]

                # climb up (levels - 1) directories
                base_dir = Path(current_file_path).parent
                for _ in range(levels - 1):
                    base_dir = base_dir.parent

                class_to_path[class_name] = str(base_dir.joinpath(*parts[:-1]).with_suffix(".py"))
            # Process each function call to add the file path
            mapped_calls = []
            for call in function_calls:
                full_name = call.get("full_name", "")
                
                # Default path is the current file if it's a simple function call
                call['file_path'] = str(Path(data.get("file_path", "unknown_file.py")).resolve())

                if "." in full_name:
                    # Handle method calls like 'self.code_finder.analyze_code_relationships'
                    parts = full_name.split(".")
                    # The variable is typically the second to last part
                    variable_name = parts[-2] if len(parts) > 1 else parts[0]

                    # Find the class of the variable
                    class_name = variable_to_class.get(variable_name)

                    if class_name:
                        # Find the file path for that class
                        path = class_to_path.get(class_name)
                        if path:
                            call['file_path'] = str(path)
                
                mapped_calls.append(call)

            return mapped_calls
        
        file_added_function_calls = create_function_call_map(file_data)
        for call in file_added_function_calls:
            caller_context = call.get('context')
            called_name = call['name']
            called_file_path = call['file_path']
            if called_name in ['print', 'len', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple']:
                continue
            debug_log(f"Processing call: {caller_context} @ {caller_file_path} calls {called_name} @ {called_file_path}")    
            if caller_context:
                session.run("""
                    // Match the caller using ITS OWN file path
                    MATCH (caller:Function {name: $caller_name, file_path: $caller_file_path})
                    
                    // Match the called function using the path we resolved
                    MATCH (called:Function {name: $called_name, file_path: $called_file_path})

                    MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(called)
                """, 
                caller_name=caller_context,
                caller_file_path=caller_file_path, # Pass the correct path for the caller
                called_name=called_name,
                called_file_path=called_file_path, # Pass the path for the called function
                line_number=call['line_number'],
                args=call.get('args', []),
                full_call_name=call.get('full_name', called_name))
                
    def _create_all_function_calls(self, all_file_data: list[Dict]):
        """Create CALLS relationships for all functions after all files have been processed."""
        with self.driver.session() as session:
            for file_data in all_file_data:
                self._create_function_calls(session, file_data)
    
    def _create_class_method_relationships(self, session, file_data: Dict):
        """Create CONTAINS relationships from classes to their methods"""
        file_path = str(Path(file_data['file_path']).resolve())
        
        for func in file_data.get('functions', []):
            class_context = func.get('class_context')
            if class_context:
                session.run("""
                    MATCH (c:Class {name: $class_name, file_path: $file_path})
                    MATCH (fn:Function {name: $func_name, file_path: $file_path, line_number: $func_line})
                    MERGE (c)-[:CONTAINS]->(fn)
                """, 
                class_name=class_context,
                file_path=file_path,
                func_name=func['name'],
                func_line=func['line_number'])
                
    def delete_file_from_graph(self, file_path: str):
        """Deletes a file and all its contained elements and relationships."""
        file_path_str = str(Path(file_path).resolve())
        with self.driver.session() as session:
            # Get parent directories
            parents_res = session.run("""
                MATCH (f:File {path: $path})<-[:CONTAINS*]-(d:Directory)
                RETURN d.path as path ORDER BY length(d.path) DESC
            """, path=file_path_str)
            parent_paths = [record["path"] for record in parents_res]

            # Delete the file and its contents
            session.run(
                """
                MATCH (f:File {path: $path})
                OPTIONAL MATCH (f)-[:CONTAINS]->(element)
                DETACH DELETE f, element
                """,
                path=file_path_str,
            )
            logger.info(f"Deleted file and its elements from graph: {file_path_str}")

            # Clean up empty parent directories, starting from the deepest
            for path in parent_paths:
                session.run("""
                    MATCH (d:Directory {path: $path})
                    WHERE NOT (d)-[:CONTAINS]->()
                    DETACH DELETE d
                """, path=path)

    def delete_repository_from_graph(self, repo_path: str):
        """Deletes a repository and all its contents from the graph."""
        repo_path_str = str(Path(repo_path).resolve())
        with self.driver.session() as session:
            session.run("""
                MATCH (r:Repository {path: $path})
                OPTIONAL MATCH (r)-[:CONTAINS*]->(e)
                DETACH DELETE r, e
            """, path=repo_path_str)
            logger.info(f"Deleted repository and its contents from graph: {repo_path_str}")

    def update_file_in_graph(self, file_path: Path):
        """Updates a file by deleting and re-adding it."""
        file_path_str = str(file_path.resolve())
        repo_name = None
        try:
            with self.driver.session() as session:
                result = session.run(
                    "MATCH (r:Repository)-[:CONTAINS]->(f:File {path: $path}) RETURN r.name as name LIMIT 1",
                    path=file_path_str
                ).single()
                if result:
                    repo_name = result["name"]
        except Exception as e:
            logger.error(f"Failed to find repository for {file_path_str}: {e}")
            return

        if not repo_name:
            logger.warning(f"Could not find repository for {file_path_str}. Aborting update.")
            return

        self.delete_file_from_graph(file_path_str)
        if file_path.exists():
            file_data = self.parse_python_file(file_path)
            if "error" not in file_data:
                self.add_file_to_graph(file_data, repo_name)
            else:
                logger.error(f"Skipping graph add for {file_path_str} due to parsing error: {file_data['error']}")
    
    def parse_python_file(self, file_path: Path, is_dependency: bool = False) -> Dict:
        """Parse a Python file and extract code elements"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
            tree = ast.parse(source_code)
            visitor = CodeVisitor(str(file_path), is_dependency)
            visitor.visit(tree)
            return {
                "file_path": str(file_path),
                "functions": visitor.functions,
                "classes": visitor.classes,
                "variables": visitor.variables,
                "imports": visitor.imports,
                "function_calls": visitor.function_calls,
                "is_dependency": is_dependency,
            }
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return {"file_path": str(file_path), "error": str(e)}

    def estimate_processing_time(self, path: Path) -> Optional[Tuple[int, float]]:
        """Estimate processing time and file count"""
        try:
            if path.is_file():
                files = [path]
            else:
                files = list(path.rglob("*.py"))
            
            total_files = len(files)
            # Simple heuristic: 0.1 seconds per file
            estimated_time = total_files * 0.1
            return total_files, estimated_time
        except Exception as e:
            logger.error(f"Could not estimate processing time for {path}: {e}")
            return None

    async def build_graph_from_path_async(
        self, path: Path, is_dependency: bool = False, job_id: str = None
    ):
        """Builds graph from a directory or file path."""
        try:
            if job_id:
                self.job_manager.update_job(job_id, status=JobStatus.RUNNING)
            
            self.add_repository_to_graph(path, is_dependency)
            repo_name = path.name

            files = list(path.rglob("*.py")) if path.is_dir() else [path]
            if job_id:
                self.job_manager.update_job(job_id, total_files=len(files))
            
            all_function_calls_data = [] # Initialize list to collect all function call data

            processed_count = 0
            for file in files:
                if file.is_file():
                    if job_id:
                        self.job_manager.update_job(job_id, current_file=str(file))
                    file_data = self.parse_python_file(file, is_dependency)
                    if "error" not in file_data:
                        self.add_file_to_graph(file_data, repo_name)
                        all_function_calls_data.append(file_data) # Collect for later processing
                    processed_count += 1
                    if job_id:
                        self.job_manager.update_job(job_id, processed_files=processed_count)
                    await asyncio.sleep(0.01)

            # After all files are processed, create function call relationships
            self._create_all_function_calls(all_function_calls_data)

            if job_id:
                self.job_manager.update_job(job_id, status=JobStatus.COMPLETED, end_time=datetime.now())
        except Exception as e:
            logger.error(f"Failed to build graph for path {path}: {e}", exc_info=True)
            if job_id:
                self.job_manager.update_job(
                    job_id, status=JobStatus.FAILED, end_time=datetime.now(), errors=[str(e)]
                )

    

    def add_code_to_graph_tool(
        self, path: str, is_dependency: bool = False
    ) -> Dict[str, Any]:
        """Tool to add code to Neo4j graph with background processing"""
        try:
            path_obj = Path(path).resolve()
            if not path_obj.exists():
                return {"error": f"Path {path} does not exist"}

            estimation = self.estimate_processing_time(path_obj)
            if estimation is None:
                return {"error": f"Could not analyze path {path}."}
            total_files, estimated_time = estimation

            job_id = self.job_manager.create_job(str(path_obj), is_dependency)
            self.job_manager.update_job(
                job_id, total_files=total_files, estimated_duration=estimated_time
            )

            # Create the coroutine for the background task
            coro = self.build_graph_from_path_async(path_obj, is_dependency, job_id)
            
            # Safely schedule the coroutine to run on the main event loop from this thread
            asyncio.run_coroutine_threadsafe(coro, self.loop)

            debug_log(f"Started background job {job_id} for path: {str(path_obj)}")

            return {
                "success": True,
                "job_id": job_id,
                "message": f"Background processing started for {path_obj}",
                "estimated_files": total_files,
                "estimated_duration_seconds": round(estimated_time, 2),
            }
        except Exception as e:
            debug_log(f"Error creating background job: {str(e)}")
            return {
                "error": f"Failed to start background processing: {e.__class__.__name__}: {e}"
            }