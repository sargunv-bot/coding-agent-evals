package taskengine

import (
    "fmt"
    "testing"

    "github.com/jackc/pgx/v5/pgtype"
    dbgen "github.com/sargunv/tend/server/internal/database/gen"
)

func hiddenAction(action dbgen.OverdueAction) dbgen.NullOverdueAction {
    return dbgen.NullOverdueAction{OverdueAction: action, Valid: true}
}

func TestHiddenOverdueActionBehaviorMatrix(t *testing.T) {
    recurrences := []dbgen.RecurrenceType{
        dbgen.RecurrenceTypeOneOff,
        dbgen.RecurrenceTypeCompletionBased,
        dbgen.RecurrenceTypeFixedNonAccumulating,
        dbgen.RecurrenceTypeFixedAccumulating,
        dbgen.RecurrenceTypeOnDependency,
    }
    actions := []dbgen.OverdueAction{
        dbgen.OverdueActionSetStatus,
        dbgen.OverdueActionClearDueDate,
        dbgen.OverdueActionAdvanceRecurrence,
    }
    status := pgtype.Text{String: "done", Valid: true}
    noStatus := pgtype.Text{}

    if err := ValidateOverdueActionRule(pgtype.Int4{}, dbgen.NullOverdueAction{}, noStatus, dbgen.RecurrenceTypeOneOff, false); err != nil {
        t.Fatalf("absent rule must remain valid: %v", err)
    }

    for _, recurrence := range recurrences {
        for _, action := range actions {
            name := fmt.Sprintf("%s/%s", recurrence, action)
            t.Run(name, func(t *testing.T) {
                actionStatus := noStatus
                if action == dbgen.OverdueActionSetStatus {
                    actionStatus = status
                }
                wantValid := action != dbgen.OverdueActionAdvanceRecurrence ||
                    recurrence == dbgen.RecurrenceTypeCompletionBased ||
                    recurrence == dbgen.RecurrenceTypeFixedNonAccumulating
                err := ValidateOverdueActionRule(pgtype.Int4{}, hiddenAction(action), actionStatus, recurrence, true)
                if wantValid && err != nil {
                    t.Fatalf("unexpected rejection: %v", err)
                }
                if !wantValid && err == nil {
                    t.Fatal("expected rejection")
                }

                if err := ValidateOverdueActionRule(pgtype.Int4{}, hiddenAction(action), actionStatus, recurrence, false); err == nil {
                    t.Fatal("a configured overdue action without a due date must be rejected")
                }
            })
        }

        if err := ValidateOverdueActionRule(
            pgtype.Int4{},
            hiddenAction(dbgen.OverdueActionSetStatus),
            noStatus,
            recurrence,
            true,
        ); err == nil {
            t.Fatal("set_status without a target status must be rejected")
        }
    }
}
