package taskengine

import (
    "strings"
    "testing"

    "github.com/jackc/pgx/v5/pgtype"
    dbgen "github.com/sargunv/tend/server/internal/database/gen"
)

func hiddenAction(a dbgen.OverdueAction) dbgen.NullOverdueAction {
    return dbgen.NullOverdueAction{OverdueAction: a, Valid: true}
}

func TestHiddenOverdueActionBehaviorMatrix(t *testing.T) {
    status := pgtype.Text{String: "done", Valid: true}
    noStatus := pgtype.Text{}
    cases := []struct {
        name       string
        action     dbgen.NullOverdueAction
        status     pgtype.Text
        recurrence dbgen.RecurrenceType
        hasDue     bool
        want       string
    }{
        {"absent rule remains valid", dbgen.NullOverdueAction{}, noStatus, dbgen.RecurrenceTypeOneOff, false, ""},
        {"set status one off", hiddenAction(dbgen.OverdueActionSetStatus), status, dbgen.RecurrenceTypeOneOff, true, ""},
        {"set status dependency", hiddenAction(dbgen.OverdueActionSetStatus), status, dbgen.RecurrenceTypeOnDependency, true, ""},
        {"clear due one off", hiddenAction(dbgen.OverdueActionClearDueDate), noStatus, dbgen.RecurrenceTypeOneOff, true, ""},
        {"clear due dependency", hiddenAction(dbgen.OverdueActionClearDueDate), noStatus, dbgen.RecurrenceTypeOnDependency, true, ""},
        {"advance one off rejected", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeOneOff, true, "only valid on recurring"},
        {"advance dependency rejected", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeOnDependency, true, "only valid on recurring"},
        {"advance completion based", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeCompletionBased, true, ""},
        {"advance fixed accumulating rejected", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeFixedAccumulating, true, "not supported on fixed_accumulating"},
        {"set status needs due", hiddenAction(dbgen.OverdueActionSetStatus), status, dbgen.RecurrenceTypeOneOff, false, "requires a due date"},
        {"clear due needs due", hiddenAction(dbgen.OverdueActionClearDueDate), noStatus, dbgen.RecurrenceTypeOnDependency, false, "requires a due date"},
        {"advance needs due", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeCompletionBased, false, "requires a due date"},
        {"set status needs status", hiddenAction(dbgen.OverdueActionSetStatus), noStatus, dbgen.RecurrenceTypeOneOff, true, "status is required"},
    }

    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            err := ValidateOverdueActionRule(pgtype.Int4{}, tc.action, tc.status, tc.recurrence, tc.hasDue)
            if tc.want == "" {
                if err != nil {
                    t.Fatalf("unexpected error: %v", err)
                }
                return
            }
            if err == nil || !strings.Contains(err.Error(), tc.want) {
                t.Fatalf("expected error containing %q, got %v", tc.want, err)
            }
        })
    }
}
