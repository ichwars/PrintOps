class OrderDomainError(Exception):
    """Base class for expected order-domain conflicts."""


class ResourceNotFoundError(OrderDomainError):
    pass


class VersionConflictError(OrderDomainError):
    pass


class InvalidStateConflictError(OrderDomainError):
    pass


class ResourceInUseError(OrderDomainError):
    pass


class DuplicateBusinessKeyError(OrderDomainError):
    pass
