package forge.spike;

import forge.game.spellability.SpellAbility;
import forge.card.mana.ManaCostShard;
import forge.game.cost.CostTap;
import java.io.IOException;
import java.util.List;

/** Chooses before activation. Unsupported source costs stop rather than becoming AI choices. */
final class ExternalManaSelection {
    static SpellAbility choose(ExternalDecisionBridge bridge, int seat, String playbook,
                               SpellAbility payingFor, ManaCostShard shard, List<SpellAbility> legal) {
        if (legal.isEmpty()) throw new UnsupportedDecision("No external mana source available");
        StringBuilder prompt = new StringBuilder("Choose the mana source to activate for ")
            .append(payingFor.getHostCard().getName()).append(" (shard ").append(shard).append("):\n");
        for (int i = 0; i < legal.size(); i++) {
            SpellAbility source = legal.get(i);
            if (!source.getPayCosts().hasOnlySpecificCostType(CostTap.class))
                throw new UnsupportedDecision("External mana source cost requires a cost prompt");
            prompt.append(i + 1).append(": ").append(source.getHostCard().getName())
                .append(" #").append(source.getHostCard().getId()).append(" ")
                .append(source.getDescription()).append('\n');
        }
        try {
            return legal.get(bridge.decide(seat, playbook, prompt.toString(), AnswerTool.Spec.one(legal.size())).option - 1);
        } catch (IOException e) {
            // Error deliberately escapes upstream catch(Exception) fallback ladders.
            throw new PilotDisconnected(e);
        }
    }

    static final class UnsupportedDecision extends Error {
        UnsupportedDecision(String message) { super(message); }
    }

    static final class PilotDisconnected extends Error {
        PilotDisconnected(IOException cause) { super("Unanswered mana decision; no source activated", cause); }
    }
}
