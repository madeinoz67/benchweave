"""Load a verified OTDP Python package without changing simulator activation.

This is an integrity boundary for trusted plugins, not a Python sandbox. Imports
inside the bundle must be relative; external dependencies are limited to stdlib.
Code and importlib.resources consume an immutable snapshot of the full inventory,
never unverified neighbouring files or a second read of the admitted cache.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib.abc
import importlib.util
import io
import json
import re
import sys
import sysconfig
from collections.abc import Iterator
from importlib.machinery import ModuleSpec
from importlib.resources.abc import Traversable, TraversableResources
from os import PathLike, fspath
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any
from uuid import uuid4

from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.registry.activation import ActivationRejected


def _safe_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ActivationRejected("unsafe_bundle_path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")):
        raise ActivationRejected("unsafe_bundle_path")
    return path


class _Resource(Traversable):
    def __init__(self, inventory: dict[str, bytes], path: str) -> None:
        self.inventory = inventory
        self.path = path.rstrip("/")

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def is_file(self) -> bool:
        return self.path in self.inventory

    def is_dir(self) -> bool:
        return any(p.startswith(self.path + "/") for p in self.inventory)

    def iterdir(self) -> Iterator[Traversable]:
        prefix = self.path + "/"
        children = {p[len(prefix) :].split("/")[0] for p in self.inventory if p.startswith(prefix)}
        return iter(self.joinpath(child) for child in sorted(children))

    def joinpath(self, *descendants: str | PathLike[str]) -> _Resource:
        path = "/".join((self.path, *(fspath(item) for item in descendants)))
        _safe_path(path)
        return _Resource(self.inventory, path)

    def read_bytes(self) -> bytes:
        with self.open("rb") as stream:
            return bytes(stream.read())

    def read_text(self, encoding: str | None = None, errors: str | None = None) -> str:
        return self.read_bytes().decode(encoding or "utf-8", errors or "strict")

    def open(self, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if mode not in {"r", "rb"}:
            raise ValueError("bundle resources are read-only")
        if not self.is_file():
            raise FileNotFoundError(self.path)
        stream = io.BytesIO(self.inventory[self.path])
        if mode == "rb":
            return stream
        return io.TextIOWrapper(stream, *args, **kwargs)


class _Resources(TraversableResources):
    def __init__(self, inventory: dict[str, bytes], directory: str) -> None:
        self.inventory = inventory
        self.directory = directory

    def files(self) -> Traversable:
        return _Resource(self.inventory, self.directory)


class _Bundle(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(
        self, prefix: str, root: str, inventory: dict[str, bytes], code_paths: set[str]
    ) -> None:
        self.prefix = prefix
        self.root = root
        self.inventory = inventory
        self.code_paths = code_paths

    def _path(self, fullname: str) -> tuple[str, bool]:
        suffix = fullname[len(self.prefix) :].replace(".", "/")
        base = self.root + suffix
        if base + "/__init__.py" in self.code_paths:
            return base + "/__init__.py", True
        if base + ".py" in self.code_paths:
            return base + ".py", False
        raise ModuleNotFoundError(f"Module is not in verified implementation inventory: {fullname}")

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        if fullname != self.prefix and not fullname.startswith(self.prefix + "."):
            return None
        _, package = self._path(fullname)
        return importlib.util.spec_from_loader(fullname, self, is_package=package)

    def create_module(self, spec: Any) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        path, package = self._path(module.__name__)
        module.__file__ = f"<verified:{self.prefix}/{path}>"
        if package:
            module.__path__ = []  # No filesystem fallback for missing submodules.
        standard_import = builtins.__import__

        def admitted_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: Any = (),
            level: int = 0,
        ) -> Any:
            if not level and name.split(".", 1)[0] not in sys.stdlib_module_names:
                raise ImportError(f"External dependency unsupported by bundle loader: {name}")
            if not level:
                top = name.split(".", 1)[0]
                spec = importlib.util.find_spec(top)
                origin = spec.origin if spec is not None else None
                if origin not in {"built-in", "frozen"}:
                    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
                    if (
                        not origin
                        or not Path(origin).resolve().is_relative_to(stdlib)
                        or "site-packages" in Path(origin).parts
                    ):
                        raise ImportError(f"Dependency does not resolve to stdlib: {name}")
            if level:
                resolved = importlib.util.resolve_name(
                    "." * level + name, (globals or {}).get("__package__", "")
                )
                if resolved != self.prefix and not resolved.startswith(self.prefix + "."):
                    raise ImportError("Relative import escapes verified package")
            return standard_import(name, globals, locals, fromlist, level)

        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": admitted_import}
        # S102: the deliberate verified-bundle execution boundary — bytes are
        # digest-checked at admission and imports run through admitted_import.
        exec(compile(self.inventory[path], module.__file__, "exec"), module.__dict__)  # noqa: S102

    def get_resource_reader(self, fullname: str) -> _Resources:
        path, package = self._path(fullname)
        if not package:
            raise ImportError("Resources require a package")
        return _Resources(self.inventory, path.rsplit("/", 1)[0])


def load_otdp_plugin(
    cache_root: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    *,
    entry_relpath: str,
    descriptor: dict[str, Any],
    services: Any,
    simulation: SimulationInfo,
    capture: Any = None,
    stream: Any = None,
) -> OTDPBridge:
    """Construct an unopened read-only bridge from an admitted package.

    The caller supplies admission's canonical manifest digest, descriptor, scoped
    OTDP services and explicit simulation declaration. Entry must be a .py module
    inside a regular package (including __init__.py), optionally under src/.
    Every Python module must have inventory role implementation. Dependencies
    outside the package are stdlib only; native extensions are not supported.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise ActivationRejected("manifest_hash_mismatch")
    encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if hashlib.sha256(encoded).hexdigest() != manifest_sha256:
        raise ActivationRejected("manifest_hash_mismatch")
    entry = _safe_path(entry_relpath)
    inventory: dict[str, bytes] = {}
    code_paths: set[str] = set()
    base = cache_root / manifest_sha256
    if base.is_symlink():
        raise ActivationRejected("unsafe_bundle_path")
    for item in manifest.get("payload", {}).get("files", []):
        relative = _safe_path(item.get("path"))
        key = str(relative)
        if key in inventory:
            raise ActivationRejected("duplicate_bundle_path")
        current = base
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ActivationRejected("unsafe_bundle_path")
        if not current.is_file():
            raise ActivationRejected("file_hash_mismatch")
        data = current.read_bytes()
        if len(data) != item.get("bytes") or hashlib.sha256(data).hexdigest() != item.get("sha256"):
            raise ActivationRejected("file_hash_mismatch")
        inventory[key] = data
        if item.get("role") == "implementation" and key.endswith(".py"):
            code_paths.add(key)
    if str(entry) not in code_paths:
        raise ActivationRejected("entry_not_implementation")
    # Find the contiguous regular-package chain; never add cache dirs to sys.path.
    root = entry.parent
    if str(root / "__init__.py") not in code_paths:
        raise ActivationRejected("entry_requires_package")
    while str(root.parent / "__init__.py") in code_paths:
        root = root.parent
    relative_module = entry.relative_to(root).with_suffix("")
    parts = list(relative_module.parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not all(part.isidentifier() for part in parts):
        raise ActivationRejected("invalid_module_path")
    prefix = f"_benchweave_otdp_{manifest_sha256}_{uuid4().hex}"
    bundle = _Bundle(prefix, str(root), inventory, code_paths)
    sys.meta_path.insert(0, bundle)

    def release() -> None:
        if bundle in sys.meta_path:
            sys.meta_path.remove(bundle)
        for name in list(sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name, None)

    try:
        module = importlib.import_module(".".join([prefix, *parts]))
        factory = getattr(module, "create_plugin", None)
        if not callable(factory):
            raise ActivationRejected("unsupported_plugin_module")
        bridge = OTDPBridge(
            factory(),
            descriptor=descriptor,
            services=services,
            simulation=simulation,
            capture=capture,
            stream=stream,
        )
        bridge._release_loader = release
        return bridge
    except BaseException:
        release()
        raise
