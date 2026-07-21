package dev.sargunv.mobilitydata.gofs.v1

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest

class ResultErrorHandlingTest {
  @Test
  fun httpErrorReturnsFailure() = runTest {
    val engine = MockEngine { respondError(HttpStatusCode.InternalServerError) }
    val client = GofsV1Client(engine)

    val result = client.getSystemManifest("https://example.com/gofs.json")

    assertTrue(result.isFailure, "Expected failure for HTTP error")
  }

  @Test
  fun waitTimesStillThrowOnInvalidArgumentsBeforeNetwork() = runTest {
    var requests = 0
    val client = GofsV1Client(MockEngine { requests += 1; error("unexpected network call") })
    val service = Service()

    context(service) {
      assertFailsWith<IllegalArgumentException> {
        client.getWaitTimes(pickupLat = 41.8781, pickupLon = -87.6298, dropOffLat = 41.9)
      }
    }
    assertEquals(0, requests)
  }

  @Test
  fun realtimeBookingsStillThrowOnInvalidArgumentsBeforeNetwork() = runTest {
    var requests = 0
    val client = GofsV1Client(MockEngine { requests += 1; error("unexpected network call") })
    val service = Service()

    context(service) {
      assertFailsWith<IllegalArgumentException> {
        client.getRealtimeBookings(
          pickupLat = 41.8781,
          pickupLon = -87.6298,
          dropOffLat = 41.9,
        )
      }
    }
    assertEquals(0, requests)
  }

  @Test
  fun thrownTransportErrorReturnsFailure() = runTest {
    val client = GofsV1Client(MockEngine { throw IOException("transport failed") })
    assertTrue(client.getSystemManifest("https://example.com/gofs.json").isFailure)
  }

  @Test
  fun malformedSuccessBodyReturnsFailure() = runTest {
    val engine = MockEngine {
      respond("not json", headers = headersOf(HttpHeaders.ContentType, "application/json"))
    }
    assertTrue(GofsV1Client(engine).getSystemManifest("https://example.com/gofs.json").isFailure)
  }

  @Test
  fun validSuccessBodyReturnsSuccess() = runTest {
    val content =
      """{"last_updated":1609866247,"ttl":0,"version":"1.0","data":{"en":{"feeds":[{"name":"system_information","url":"https://example.com/info"}]}}}"""
    val engine = MockEngine {
      respond(content, headers = headersOf(HttpHeaders.ContentType, "application/json"))
    }
    assertTrue(GofsV1Client(engine).getSystemManifest("https://example.com/gofs.json").isSuccess)
  }

  @Test
  fun validCoordinatesThenTransportErrorReturnsFailure() = runTest {
    val client = GofsV1Client(MockEngine { throw IOException("transport failed") })
    val service = Service(FeedType.WaitTimes to "https://example.com/wait-times")
    context(service) {
      val result =
        client.getWaitTimes(
          pickupLat = 41.8781,
          pickupLon = -87.6298,
          dropOffLat = 41.9,
          dropOffLon = -87.6,
        )
      assertTrue(result.isFailure)
    }
  }
}
