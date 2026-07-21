package dev.sargunv.mobilitydata.gbfs.v2

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import java.io.File
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest

class ResultErrorHandlingTest {
  @Test
  fun networkErrorReturnsFailure() = runTest {
    val engine = MockEngine { respondError(HttpStatusCode.InternalServerError) }
    val client = GbfsV2Client(engine)

    val result = client.getSystemManifest("https://example.com/gbfs.json")

    assertTrue(result.isFailure, "Expected failure for network error")
  }

  @Test
  fun notFoundReturnsFailure() = runTest {
    val engine = MockEngine { respondError(HttpStatusCode.NotFound) }
    val client = GbfsV2Client(engine)

    val result = client.getSystemManifest("https://example.com/gbfs.json")

    assertTrue(result.isFailure, "Expected failure for 404 error")
  }

  @Test
  fun thrownTransportErrorReturnsFailure() = runTest {
    val client = GbfsV2Client(MockEngine { throw IOException("transport failed") })
    assertTrue(client.getSystemManifest("https://example.com/gbfs.json").isFailure)
  }

  @Test
  fun malformedSuccessBodyReturnsFailure() = runTest {
    val engine = MockEngine {
      respond("not json", headers = headersOf(HttpHeaders.ContentType, "application/json"))
    }
    assertTrue(GbfsV2Client(engine).getSystemManifest("https://example.com/gbfs.json").isFailure)
  }

  @Test
  fun missingFeedReturnsFailureBeforeNetwork() = runTest {
    var requests = 0
    val client = GbfsV2Client(MockEngine { requests += 1; error("unexpected network call") })
    context(Service()) { assertTrue(client.getSystemInformation().isFailure) }
    assertEquals(0, requests)
  }

  @Test
  fun validSuccessBodyReturnsSuccess() = runTest {
    val content = File("/app/sample-data/gbfs-v2/bird/gbfs.json").readText()
    val engine = MockEngine {
      respond(content, headers = headersOf(HttpHeaders.ContentType, "application/json"))
    }
    assertTrue(GbfsV2Client(engine).getSystemManifest("https://example.com/gbfs.json").isSuccess)
  }
}
