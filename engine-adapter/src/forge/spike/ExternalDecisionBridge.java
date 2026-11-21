package forge.spike;

import com.google.gson.*;
import java.io.*;
import java.util.Objects;

/** Blocking referee channel. Invalid input cannot return a strategic answer. */
final class ExternalDecisionBridge {
    private final BufferedReader input;
    private final PrintWriter output;
    private final String gameId;
    private long revision;
    private JsonObject acceptedReply;
    private JsonObject acceptedAck;

    ExternalDecisionBridge(Reader input, Writer output, String gameId) {
        this.input = new BufferedReader(input);
        this.output = new PrintWriter(output, true);
        this.gameId = Objects.requireNonNull(gameId);
    }

    synchronized AnswerTool.Answer decide(int seat, String playbook, String observation,
                                          AnswerTool.Spec spec) throws IOException {
        if (seat != 0 && seat != 1) throw new IllegalArgumentException("seat must be 0 or 1");
        long current = ++revision;
        JsonObject request = new JsonObject();
        request.addProperty("protocol_version", 1);
        request.addProperty("game_id", gameId);
        request.addProperty("seat", seat);
        request.addProperty("decision_id", gameId + ":" + current);
        request.addProperty("state_revision", current);
        request.addProperty("playbook_version", playbook);
        JsonObject view = new JsonObject();
        view.add("public", new JsonObject());
        JsonObject privateView = new JsonObject();
        privateView.addProperty("observation", observation);
        view.add("private", privateView);
        request.add("view", view);
        JsonObject action = new JsonObject();
        action.addProperty("action_id", "answer");
        action.addProperty("label", AnswerTool.instruction(spec, false));
        action.add("parameters_schema", AnswerTool.definition(spec).getAsJsonObject("function").getAsJsonObject("parameters"));
        JsonArray actions = new JsonArray();
        actions.add(action);
        request.add("legal_actions", actions);
        output.println(request);
        if (output.checkError()) throw new IOException("Decision channel write failed");
        while (true) {
            String line = input.readLine();
            if (line == null) throw new EOFException("External pilot disconnected with unapplied decision " + current);
            try {
                JsonObject reply = JsonParser.parseString(line).getAsJsonObject();
                if (acceptedReply != null && acceptedReply.equals(reply)) {
                    output.println(acceptedAck);
                    continue;
                }
                for (String field : new String[]{"game_id", "seat", "decision_id", "state_revision"}) {
                    if (!request.get(field).equals(reply.get(field)))
                        throw new IllegalArgumentException("Decision identity mismatch: " + field);
                }
                if (!new JsonPrimitive("answer").equals(reply.get("action_id")))
                    throw new IllegalArgumentException("Unknown action_id");
                if (!reply.has("parameters") || !reply.get("parameters").isJsonObject())
                    throw new IllegalArgumentException("parameters must be an object");
                AnswerTool.Result result = AnswerTool.validate(spec, reply.get("parameters").toString());
                if (result.error != null) throw new IllegalArgumentException(result.error);
                acceptedReply = reply.deepCopy();
                acceptedAck = new JsonObject();
                acceptedAck.addProperty("type", "accepted");
                for (String field : new String[]{"game_id", "seat", "decision_id", "state_revision"})
                    acceptedAck.add(field, request.get(field));
                acceptedAck.addProperty("provenance", "external");
                acceptedAck.add("action_id", reply.get("action_id"));
                acceptedAck.add("parameters", reply.get("parameters").deepCopy());
                output.println(acceptedAck);
                if (output.checkError()) throw new IOException("Acceptance channel write failed");
                return result.answer;
            } catch (JsonParseException | IllegalArgumentException | IllegalStateException | NullPointerException invalid) {
                JsonObject error = new JsonObject();
                error.addProperty("type", "paused");
                error.addProperty("decision_id", gameId + ":" + current);
                error.addProperty("reason", invalid.getMessage());
                output.println(error);
            }
        }
    }
}
