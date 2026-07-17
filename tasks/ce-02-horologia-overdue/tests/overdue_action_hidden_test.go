package taskengine

import (
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
        wantErr    bool
    }{
        {"absent rule remains valid", dbgen.NullOverdueAction{}, noStatus, dbgen.RecurrenceTypeOneOff, false, false},
        {"set status one off", hiddenAction(dbgen.OverdueActionSetStatus), status, dbgen.RecurrenceTypeOneOff, true, false},
        {"set status dependency", hiddenAction(dbgen.OverdueActionSetStatus), status, dbgen.RecurrenceTypeOnDependency, true, false},
        {"clear due one off", hiddenAction(dbgen.OverdueActionClearDueDate), noStatus, dbgen.RecurrenceTypeOneOff, true, false},
        {"clear due dependency", hiddenAction(dbgen.OverdueActionClearDueDate), noStatus, dbgen.RecurrenceTypeOnDependency, true, false},
        {"advance one off rejected", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeOneOff, true, true},
        {"advance dependency rejected", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeOnDependency, true, true},
        {"advance completion based", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeCompletionBased, true, false},
        {"advance fixed accumulating rejected", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeFixedAccumulating, true, true},
        {"set status needs due", hiddenAction(dbgen.OverdueActionSetStatus), status, dbgen.RecurrenceTypeOneOff, false, true},
        {"clear due needs due", hiddenAction(dbgen.OverdueActionClearDueDate), noStatus, dbgen.RecurrenceTypeOnDependency, false, true},
        {"advance needs due", hiddenAction(dbgen.OverdueActionAdvanceRecurrence), noStatus, dbgen.RecurrenceTypeCompletionBased, false, true},
        {"set status needs status", hiddenAction(dbgen.OverdueActionSetStatus), noStatus, dbgen.RecurrenceTypeOneOff, true, true},
    }

    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            err := ValidateOverdueActionRule(pgtype.Int4{}, tc.action, tc.status, tc.recurrence, tc.hasDue)
            if tc.wantErr && err == nil {
                t.Fatal("expected validation rejection, got nil")
            }
            if !tc.wantErr && err != nil {
                t.Fatalf("unexpected validation rejection: %v", err)
            }
        })
    }
}
