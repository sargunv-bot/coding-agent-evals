package dev.sargunv.mobilitydata.gofs.v1

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respondError
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest

class ResultErrorHandlingTest {
  @Test
  fun networkErrorReturnsFailure() = runTest {
    val engine = MockEngine { respondError(HttpStatusCode.InternalServerError) }
    val client = GofsV1Client(engine)
    assertTrue(client.getSystemManifest("https://example.com/gofs.json").isFailure)
  }

  @Test
  fun invalidWaitTimesArgumentsReturnFailureWithoutNetwork() = runTest {
    val client = GofsV1Client(MockEngine { error("unexpected network call") })
    context(Service(FeedType.WaitTimes to "https://example.com/wait-times.json")) {
      val result = client.getWaitTimes(
        pickupLat = 41.8781,
        pickupLon = -87.6298,
        dropOffLat = 41.9,
      )
      assertTrue(result.isFailure)
      assertIs<IllegalArgumentException>(result.exceptionOrNull())
    }
  }

  @Test
  fun invalidRealtimeBookingsArgumentsReturnFailureWithoutNetwork() = runTest {
    val client = GofsV1Client(MockEngine { error("unexpected network call") })
    context(
      Service(FeedType.RealtimeBookings to "https://example.com/realtime-bookings.json")
    ) {
      val result = client.getRealtimeBookings(
        pickupLat = 41.8781,
        pickupLon = -87.6298,
        dropOffLat = 41.9,
      )
      assertTrue(result.isFailure)
      assertIs<IllegalArgumentException>(result.exceptionOrNull())
    }
  }
}
