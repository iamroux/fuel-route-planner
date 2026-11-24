class PlannerError(Exception):
    status = 500


class InputError(PlannerError):
    status = 400


class NoRouteError(PlannerError):
    status = 422


class UpstreamError(PlannerError):
    status = 502
