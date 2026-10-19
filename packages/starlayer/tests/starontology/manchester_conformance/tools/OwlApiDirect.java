import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.formats.TurtleDocumentFormat;
import org.semanticweb.owlapi.io.StringDocumentSource;
import org.semanticweb.owlapi.model.MissingImportHandlingStrategy;
import org.semanticweb.owlapi.model.OWLOntology;
import org.semanticweb.owlapi.model.OWLOntologyLoaderConfiguration;
import org.semanticweb.owlapi.model.OWLOntologyManager;

/**
 * Loads each Manchester Syntax document straight into the OWL API (no scratch ontology, no merging) and
 * writes it back as Turtle, in one JVM for the whole corpus.
 *
 * The older harness (OWLAPIInterface "parse") merges only the *axioms* of a scratch ontology into its own,
 * so the ontology IRI, version IRI and ontology annotations never reach its output. This runner keeps them.
 *
 * stdin:  [ {"id": "...", "text": "..."} , ... ]
 * stdout: [ {"id": "...", "accepted": true, "turtle": "..."} | {"id": "...", "accepted": false, "error": "..."} ]
 */
public class OwlApiDirect {
    public static void main(String[] args) throws Exception {
        String in = new String(System.in.readAllBytes(), "UTF-8");
        JsonArray cases = JsonParser.parseString(in).getAsJsonArray();
        JsonArray out = new JsonArray();
        for (JsonElement element : cases) {
            JsonObject c = element.getAsJsonObject();
            JsonObject r = new JsonObject();
            r.addProperty("id", c.get("id").getAsString());
            try {
                OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
                OWLOntologyLoaderConfiguration config = new OWLOntologyLoaderConfiguration()
                    .setMissingImportHandlingStrategy(MissingImportHandlingStrategy.SILENT);
                OWLOntology ontology = manager.loadOntologyFromOntologyDocument(
                    new StringDocumentSource(c.get("text").getAsString()), config);
                TurtleDocumentFormat format = new TurtleDocumentFormat();
                format.setDefaultPrefix("http://example.org/o#");
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                manager.saveOntology(ontology, format, bytes);
                r.addProperty("accepted", true);
                r.addProperty("turtle", bytes.toString("UTF-8"));
            } catch (Throwable t) {
                r.addProperty("accepted", false);
                r.addProperty("error", String.valueOf(t.getMessage()));
            }
            out.add(r);
        }
        System.out.println(new Gson().toJson(out));
    }
}
