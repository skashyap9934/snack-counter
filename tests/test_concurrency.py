from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Barrier

from snack_counter.models import OfficeId, RefillStatus
from tests.conftest import volunteer


def test_two_people_cannot_both_commit_to_the_same_refill(service, now):
    """Even if both pass the first status check, the store lock keeps one winner."""
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    service.register_volunteer(volunteer("lars", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    assignee = refill.assigned_to
    other = "lars" if assignee == "ida" else "ida"

    barrier = Barrier(2)
    results: list[str] = []

    def try_commit(employee_id: str) -> str:
        barrier.wait()
        try:
            service.commit(refill.id, employee_id)
            return f"ok:{employee_id}"
        except Exception as exc:
            return f"err:{employee_id}:{type(exc).__name__}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(try_commit, assignee),
            pool.submit(try_commit, other),
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    oks = [r for r in results if r.startswith("ok:")]
    assert oks == [f"ok:{assignee}"]
    assert service.store.get_refill(refill.id).status == RefillStatus.COMMITTED
    assert service.store.get_refill(refill.id).assigned_to == assignee


def test_double_commit_by_same_person_second_call_fails(service, now):
    service.register_volunteer(volunteer("ida", OfficeId.OSLO, now.date()))
    refill = service.report_empty(OfficeId.OSLO, "ida")
    service.commit(refill.id, "ida")
    barrier = Barrier(2)

    def again() -> str:
        barrier.wait()
        try:
            service.commit(refill.id, "ida")
            return "ok"
        except Exception as exc:
            return type(exc).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(again), pool.submit(again)]]

    assert results.count("ok") == 0
    assert "InvalidTransitionError" in results
