-- Replace table/columns with a reviewed SELECT over your source's approved view.
SELECT id, period, category, currency, budget_minor, actual_minor
FROM approved_budget_view
WHERE period = :period
ORDER BY id
