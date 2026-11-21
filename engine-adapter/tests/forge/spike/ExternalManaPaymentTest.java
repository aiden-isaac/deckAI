package forge.spike;

import forge.GuiDesktop;
import forge.ai.*;
import forge.card.mana.*;
import forge.deck.Deck;
import forge.game.*;
import forge.game.ability.AbilityFactory;
import forge.game.card.Card;
import forge.game.mana.ManaCostBeingPaid;
import forge.game.player.*;
import forge.game.spellability.SpellAbility;
import forge.game.zone.ZoneType;
import forge.gui.GuiBase;
import forge.model.FModel;
import java.io.*;
import java.util.*;

/** Real Forge payment, with scripted external replies; not a CLI-piloted game. */
public final class ExternalManaPaymentTest {
    static final class Controller extends PlayerControllerAi implements ComputerUtilMana.ExternalManaController {
        final ExternalDecisionBridge bridge;
        SpellAbility selected;
        Controller(Player p, LobbyPlayerAi lobby, Reader in, Writer out) {
            super(p.getGame(), p, lobby);
            bridge = new ExternalDecisionBridge(in, out, "game");
        }
        public SpellAbility chooseManaSource(SpellAbility payingFor, ManaCostShard shard, List<SpellAbility> legal) {
            // Stable fixture ordering makes the two scripted replies name different physical lands.
            List<SpellAbility> ordered = new ArrayList<>(legal);
            ordered.sort(Comparator.comparing(a -> a.getHostCard().getName()));
            selected = ExternalManaSelection.choose(bridge, 0, "fixture-v1", payingFor, shard, ordered);
            return selected;
        }
    }
    static void run(int option) throws Exception {
        StringWriter transcript = new StringWriter();
        PipedWriter pendingWriter = option == 0 ? new PipedWriter() : null;
        Reader input = option == 0 ? new PipedReader(pendingWriter)
            : new StringReader(ExternalDecisionBridgeTest.answer("1",0,1,option));
        LobbyPlayerAi lobby = new LobbyPlayerAi("external fixture", null) {
            @Override public Player createIngamePlayer(Game game, int id) {
                Player p = new Player(getName(), game, id);
                p.setFirstController(new Controller(p, this,
                    input, transcript));
                return p;
            }
        };
        lobby.setAiProfile("Default");
        RegisteredPlayer a = new RegisteredPlayer(new Deck()).setPlayer(lobby);
        RegisteredPlayer b = new RegisteredPlayer(new Deck()).setPlayer(new LobbyPlayerAi("unused", null));
        Match match = new Match(new GameRules(GameType.Constructed), Arrays.asList(a,b), "payment fixture");
        Game game = match.createGame();
        Player p = game.getPlayers().get(0);
        Controller c = (Controller)p.getController();
        Card island = Card.fromPaperCard(FModel.getMagicDb().getCommonCards().getCard("Island"), p);
        Card mountain = Card.fromPaperCard(FModel.getMagicDb().getCommonCards().getCard("Mountain"), p);
        p.getZone(ZoneType.Battlefield).add(island);
        p.getZone(ZoneType.Battlefield).add(mountain);
        island.setSickness(false); mountain.setSickness(false);
        SpellAbility sa = AbilityFactory.getAbility("AB$ Draw | Cost$ 1 | NumCards$ 1", island);
        sa.setActivatingPlayer(p);
        try {
            if (option == 0) {
                java.util.concurrent.FutureTask<Boolean> pending = new java.util.concurrent.FutureTask<>(() ->
                    ComputerUtilMana.payManaCost(new ManaCostBeingPaid(new ManaCost("1")), sa, p, false));
                Thread worker = new Thread(pending, "unanswered-payment-fixture");
                worker.start();
                try {
                    pending.get(300, java.util.concurrent.TimeUnit.MILLISECONDS);
                    throw new AssertionError("Unanswered decision returned");
                } catch (java.util.concurrent.TimeoutException expected) {
                    if (!transcript.toString().contains("legal_actions") || island.isTapped() || mountain.isTapped())
                        throw new AssertionError("Payment did not remain pending without tapping");
                } finally {
                    pendingWriter.close();
                }
                try {
                    pending.get(5, java.util.concurrent.TimeUnit.SECONDS);
                    throw new AssertionError("EOF returned a payment");
                } catch (java.util.concurrent.ExecutionException stopped) {
                    if (!(stopped.getCause() instanceof ExternalManaSelection.PilotDisconnected)) throw stopped;
                }
                if (island.isTapped() || mountain.isTapped() || c.selected != null) throw new AssertionError("Unanswered mutated payment");
                System.out.println("PASS option=0 pending then EOF: both lands untapped, no selection");
                System.out.print(transcript);
                return;
            }
            if (!ComputerUtilMana.payManaCost(new ManaCostBeingPaid(new ManaCost("1")), sa, p, false))
                throw new AssertionError("Payment failed");
            if (option == 0) throw new AssertionError("Unanswered payment succeeded");
            if (island.isTapped() != (option == 1) || mountain.isTapped() != (option == 2))
                throw new AssertionError("Wrong land tapped: " + transcript);
            if (c.selected.getHostCard() != (option == 1 ? island : mountain)) throw new AssertionError("Wrong provenance");
            if (!transcript.toString().contains("\"provenance\":\"external\"")) throw new AssertionError("Missing acceptance");
        } catch (ExternalManaSelection.PilotDisconnected e) {
            if (option != 0 || island.isTapped() || mountain.isTapped()) throw new AssertionError("Unanswered mutated payment",e);
        }
        System.out.println("PASS option="+option+" Island.tapped="+island.isTapped()+" Mountain.tapped="+mountain.isTapped());
        System.out.print(transcript);
    }
    public static void main(String[] args) {
        try {
            GuiBase.setInterface(new GuiDesktop());
            FModel.initialize(null, null);
            ComputerUtilMana.HARNESS_SEAT_PAYS_BY_RULES = p -> p.getController() instanceof Controller;
            run(1); run(2); run(0);
            System.exit(0);
        } catch (Throwable t) { t.printStackTrace(); System.exit(1); }
    }
}
