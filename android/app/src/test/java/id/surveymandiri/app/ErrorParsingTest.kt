package id.surveymandiri.app

import com.google.gson.JsonParser
import id.surveymandiri.app.data.parseErrorBody
import id.surveymandiri.app.data.questions
import id.surveymandiri.app.data.stringField
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ErrorParsingTest {
    @Test
    fun validationErrorShowsFirstFieldMessage() {
        val body = """{"error":{"code":"validation_error","message":"Invalid input.","details":{"email":["Email already registered."]}}}"""
        val e = parseErrorBody(body, 400)
        assertEquals("email: Email already registered.", e.message)
        assertEquals("validation_error", e.code)
    }

    @Test
    fun nestedDetailsAreFlattened() {
        val body = """{"error":{"code":"validation_error","message":"Invalid input.","details":{"details":{"questions":["Ensure this field has at least 1 elements."]}}}}"""
        assertEquals("details: questions: Ensure this field has at least 1 elements.", parseErrorBody(body, 400).message)
    }

    @Test
    fun businessErrorKeepsServerMessage() {
        val body = """{"error":{"code":"quota_full","message":"Only 1 units left.","details":{}}}"""
        val e = parseErrorBody(body, 409)
        assertEquals("Only 1 units left.", e.message)
        assertEquals(409, e.httpStatus)
    }

    @Test
    fun nonJsonBodyFallsBackToStatus() {
        val e = parseErrorBody("<html>Bad Gateway</html>", 502)
        assertTrue(e.message!!.contains("502"))
    }

    @Test
    fun questionsAreReadFromDetails() {
        val details = JsonParser.parseString("""{"electoral_district":"Jabar 4","questions":["Pilihan Anda?","Alasan?"]}""").asJsonObject
        assertEquals(listOf("Pilihan Anda?", "Alasan?"), details.questions())
        assertEquals("Jabar 4", details.stringField("electoral_district"))
        assertEquals(emptyList<String>(), (null as com.google.gson.JsonObject?).questions())
    }
}
