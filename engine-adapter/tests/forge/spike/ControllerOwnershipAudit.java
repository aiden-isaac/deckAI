package forge.spike;

import forge.game.player.PlayerController;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.*;

/** Inventory, not a safety certificate: inherited methods require explicit classification. */
public final class ControllerOwnershipAudit {
    public static void main(String[] args) throws Exception {
        List<String> rows = new ArrayList<>();
        for (Method callback : PlayerController.class.getMethods()) {
            if (callback.getDeclaringClass() == Object.class || Modifier.isStatic(callback.getModifiers())) continue;
            Method implementation = LlmSpikeGui.PlayerControllerLLM.class.getMethod(callback.getName(), callback.getParameterTypes());
            rows.add(callback.getName() + Arrays.toString(callback.getParameterTypes()) + "\t" + implementation.getDeclaringClass().getName());
        }
        Collections.sort(rows);
        System.out.println("callback\timplementation");
        rows.forEach(System.out::println);
    }
}
