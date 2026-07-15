"""
轻量级依赖注入容器

提供零外部依赖的 DI 能力，支持：
- 单例 / 瞬态注册
- 工厂方法注册
- 惰性解析
- 测试时重置
"""

from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar("T")


class _Registration:
    """单个依赖注册项"""

    def __init__(
        self,
        impl: Any = None,
        factory: Optional[Callable[[], Any]] = None,
        singleton: bool = True,
    ):
        self._impl = impl
        self._factory = factory
        self._singleton = singleton
        self._instance: Optional[Any] = None

    def resolve(self) -> Any:
        if self._singleton:
            if self._instance is None:
                self._instance = self._build()
            return self._instance
        return self._build()

    def _build(self) -> Any:
        if self._factory is not None:
            return self._factory()
        if self._impl is not None:
            if callable(self._impl) and not isinstance(self._impl, (str, int, float, bool)):
                # Assume it's a class to instantiate
                try:
                    return self._impl()
                except TypeError:
                    pass
            return self._impl
        raise RuntimeError("No implementation or factory registered")


class DependencyNotFoundError(KeyError):
    """Raised when a dependency is not registered in the container."""
    pass


class DIContainer:
    """依赖注入容器（线程不安全 —— 仅在启动阶段注册，运行时只读）"""

    def __init__(self):
        self._registrations: Dict[str, _Registration] = {}

    # ---- registration ----

    def register(
        self,
        name: str,
        implementation: Any,
        singleton: bool = True,
    ) -> "DIContainer":
        """注册一个具体实现或值。

        Args:
            name: 依赖标识符（通常用接口/类名）
            implementation: 具体实现类或值
            singleton: 是否单例（默认 True）

        Returns:
            self，便于链式调用
        """
        self._registrations[name] = _Registration(
            impl=implementation,
            singleton=singleton,
        )
        return self

    def register_factory(
        self,
        name: str,
        factory: Callable[[], Any],
        singleton: bool = True,
    ) -> "DIContainer":
        """通过工厂方法注册。

        Args:
            name: 依赖标识符
            factory: 无参可调用对象，返回依赖实例
            singleton: 是否单例（默认 True）

        Returns:
            self，便于链式调用
        """
        self._registrations[name] = _Registration(
            factory=factory,
            singleton=singleton,
        )
        return self

    def register_instance(self, name: str, instance: Any) -> "DIContainer":
        """注册一个已创建的实例（始终单例）。"""
        self._registrations[name] = _Registration(impl=instance, singleton=True)
        self._registrations[name]._instance = instance
        return self

    # ---- resolution ----

    def resolve(self, name: str) -> Any:
        """解析依赖。"""
        reg = self._registrations.get(name)
        if reg is None:
            raise DependencyNotFoundError(
                f"Dependency '{name}' is not registered. "
                f"Available: {list(self._registrations.keys())}"
            )
        return reg.resolve()

    def resolve_or_none(self, name: str) -> Optional[Any]:
        """解析依赖，未注册时返回 None 而非抛出异常。"""
        reg = self._registrations.get(name)
        if reg is None:
            return None
        return reg.resolve()

    def registered(self, name: str) -> bool:
        """检查依赖是否已注册。"""
        return name in self._registrations

    # ---- lifecycle ----

    def reset(self) -> None:
        """清空所有注册（主要用于测试）。"""
        self._registrations.clear()

    def registered_names(self) -> list:
        """返回所有已注册的依赖名称。"""
        return list(self._registrations.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._registrations


# ---------------------------
# 全局容器实例
# ---------------------------
_container: Optional[DIContainer] = None


def get_container() -> DIContainer:
    """获取全局 DI 容器。"""
    global _container
    if _container is None:
        _container = DIContainer()
    return _container


def reset_container() -> None:
    """重置全局容器（测试用）。"""
    global _container
    _container = None


# ---------------------------
# 便捷装饰器（可选）
# ---------------------------

def inject(container: Optional[DIContainer] = None):
    """简单的属性注入装饰器。

    Usage:
        @inject()
        class MyService:
            repo: Repository = None  # 由容器自动注入

        container.register('Repository', MyRepo)
        svc = MyService()
        # svc.repo 现在是 MyRepo 实例
    """
    def decorator(cls):
        original_init = cls.__init__

        def new_init(self, *args, **kwargs):
            c = container or get_container()
            for attr_name, attr_type in cls.__annotations__.items():
                if attr_name not in kwargs:
                    dep_name = getattr(attr_type, "__name__", attr_name)
                    try:
                        kwargs[attr_name] = c.resolve(dep_name)
                    except DependencyNotFoundError:
                        # Try resolving by attribute name as fallback
                        try:
                            kwargs[attr_name] = c.resolve(attr_name)
                        except DependencyNotFoundError:
                            pass
            original_init(self, *args, **kwargs)

        cls.__init__ = new_init
        return cls

    return decorator
