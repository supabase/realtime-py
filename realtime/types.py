import sys
from typing import Callable, TypeVar

if sys.version_info > (3, 9):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec


T_ParamSpec = ParamSpec("T_ParamSpec")
T_Retval = TypeVar("T_Retval")

# Custom types
Callback = Callable[T_ParamSpec, T_Retval]
