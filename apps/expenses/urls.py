
from django.urls import path

from .views import (
    ExpenseCreateListView,
    GroupExpenseListView,
    ExpenseDetailView,
)

urlpatterns = [
    path(
        "expenses/",
        ExpenseCreateListView.as_view(),
        name="expense-create",
    ),
    path(
        "groups/<str:group_id>/expenses/",
        GroupExpenseListView.as_view(),
        name="group-expenses",
    ),
    path(
        "expenses/<str:expense_id>/",
        ExpenseDetailView.as_view(),
        name="expense-detail",
    ),
]


# Method	Endpoint	Purpose
# POST	/api/v1/expenses/	Create an expense
# GET	/api/v1/groups/{group_id}/expenses/	List group expenses
# GET	/api/v1/expenses/{expense_id}/	View one expense
# PATCH	/api/v1/expenses/{expense_id}/	Edit creator's expense
# DELETE	/api/v1/expenses/{expense_id}/	Soft-delete creator's expense