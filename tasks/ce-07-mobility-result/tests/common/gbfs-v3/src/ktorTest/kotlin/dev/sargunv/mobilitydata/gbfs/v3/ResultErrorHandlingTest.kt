package dev.sargunv.mobilitydata.gbfs.v3

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import java.io.File
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest

class ResultErrorHandlingTest {
  @Test
  fun networkErrorReturnsFailure() = runTest {
    val engine = MockEngine { respondError(HttpStatusCode.InternalServerError) }
    val client = GbfsV3Client(engine)

    val result = client.getServiceManifest("https://example.com/gbfs.json")

    assertTrue(result.isFailure, "Expected failure for network error")
  }

  @Test
  fun notFoundReturnsFailure() = runTest {
    val engine = MockEngine { respondError(HttpStatusCode.NotFound) }
    val client = GbfsV3Client(engine)

    val result = client.getServiceManifest("https://example.com/gbfs.json")

    assertTrue(result.isFailure, "Expected failure for 404 error")
  }

  @Test
  fun thrownTransportErrorReturnsFailure() = runTest {
    val client = GbfsV3Client(MockEngine { throw IOException("transport failed") })
    assertTrue(client.getServiceManifest("https://example.com/gbfs.json").isFailure)
  }

  @Test
  fun malformedSuccessBodyReturnsFailure() = runTest {
    val engine = MockEngine {
      respond("not json", headers = headersOf(HttpHeaders.ContentType, "application/json"))
    }
    assertTrue(GbfsV3Client(engine).getServiceManifest("https://example.com/gbfs.json").isFailure)
  }

  @Test
  fun validSuccessBodyReturnsSuccess() = runTest {
    val content = File("/app/sample-data/gbfs-v3/flamingo/gbfs.json").readText()
    val engine = MockEngine {
      respond(content, headers = headersOf(HttpHeaders.ContentType, "application/json"))
    }
    assertTrue(GbfsV3Client(engine).getServiceManifest("https://example.com/gbfs.json").isSuccess)
  }
}
