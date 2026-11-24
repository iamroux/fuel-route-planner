import json
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .errors import InputError, PlannerError
from .planner import plan_trip


def _read_inputs(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body or b'{}')
        except json.JSONDecodeError as exc:
            raise InputError('Request body must be JSON like {"start": "...", "finish": "..."}.') from exc
        if not isinstance(body, dict):
            raise InputError('Request body must be a JSON object.')
        start, finish = body.get('start'), body.get('finish')
    else:
        start, finish = request.GET.get('start'), request.GET.get('finish')

    if not isinstance(start, str) or not isinstance(finish, str) or not start.strip() or not finish.strip():
        raise InputError('Both "start" and "finish" are required, e.g. "Dallas, TX" or "32.78,-96.80".')

    penalty = (body if request.method == 'POST' else request.GET).get('stop_penalty')
    if penalty is not None and penalty != '':
        try:
            penalty = float(penalty)
        except (TypeError, ValueError):
            raise InputError('"stop_penalty" must be a number of dollars, e.g. 0 or 5.') from None
        if not 0 <= penalty <= 100:
            raise InputError('"stop_penalty" must be between 0 and 100.')
    else:
        penalty = None
    return start.strip(), finish.strip(), penalty


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def route_plan(request):
    try:
        start, finish, penalty = _read_inputs(request)
        result = plan_trip(start, finish, penalty)
    except PlannerError as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)

    params = {'start': start, 'finish': finish}
    if penalty is not None:
        params['stop_penalty'] = penalty
    query = urlencode(params)
    result['map_url'] = request.build_absolute_uri(f"{reverse('route-map')}?{query}")
    return JsonResponse(result)


@require_GET
def route_map(request):
    try:
        start, finish, penalty = _read_inputs(request)
        result = plan_trip(start, finish, penalty)
    except PlannerError as exc:
        return render(request, 'routing/map.html', {'error': str(exc)}, status=exc.status)
    return render(request, 'routing/map.html', {'plan': result})
