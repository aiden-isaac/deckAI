package forge.spike;
import java.io.*;
import com.google.gson.*;

public final class ExternalDecisionBridgeTest {
    static String answer(String decision, int seat, long revision, int option) {
        return "{\"game_id\":\"game\",\"seat\":"+seat+",\"decision_id\":\"game:"+decision+"\",\"state_revision\":"+revision+",\"action_id\":\"answer\",\"parameters\":{\"option\":"+option+"}}\n";
    }
    public static void main(String[] args) throws Exception {
        String accepted = answer("1",0,1,2);
        String input = "{broken\n" + answer("1",1,1,1) + answer("1",0,1,3) + accepted + accepted + answer("2",1,2,1);
        StringWriter output = new StringWriter();
        ExternalDecisionBridge bridge = new ExternalDecisionBridge(new StringReader(input),output,"game");
        if (bridge.decide(0,"v1","own secret",AnswerTool.Spec.one(2)).option != 2) throw new AssertionError();
        if (bridge.decide(1,"v2","other secret",AnswerTool.Spec.one(2)).option != 1) throw new AssertionError();
        String[] rows=output.toString().split("\n");
        if (rows.length!=8) throw new AssertionError(output.toString());
        JsonObject prompt=JsonParser.parseString(rows[0]).getAsJsonObject();
        if (!prompt.getAsJsonArray("legal_actions").get(0).getAsJsonObject().get("parameters_schema").isJsonObject()) throw new AssertionError();
        if (!rows[5].contains("other secret") || rows[5].contains("own secret")) throw new AssertionError();
        try {
            new ExternalDecisionBridge(new StringReader(""),new StringWriter(),"game")
                .decide(0,"v1","",AnswerTool.Spec.one(2));
            throw new AssertionError("EOF chose an action");
        } catch (EOFException expected) { }
        System.out.println("PASS: identity, invalid option, duplicate acknowledgement, schema, seat-local payload, EOF refusal");
    }
}
