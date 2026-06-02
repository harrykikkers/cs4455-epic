"""Unit tests for MessageAPI (api/messages.py) — request shape.

The crypto fields are produced upstream by ``crypto.messaging.seal``; this
suite only asserts that the API wrapper sends them to the right endpoint in the
right shape — in particular that the abandoned ``enc`` field is gone from both
the send and forward bodies, and that a forward targets the original message id.
"""
import json

import pytest
import responses

from api.messages import MessageAPI
from session import Session

DIGEST = "0x" + "ab" * 32
MID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def api():
    s = Session()
    s.set("tok123", "me-id", "me")
    return MessageAPI(session=s, base_url="https://test.local")


@responses.activate
def test_forward_posts_sealed_envelope_without_enc(api):
    responses.add(responses.POST,
                  f"https://test.local/api/messages/{MID}/forward",
                  json={"data": {"id": "share-1"}}, status=201)

    api.forward(MID, "rid-2", "CT", "NONCE16CHARSXXX=", "SIG", 7, DIGEST)

    assert len(responses.calls) == 1
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {
        "recipientId": "rid-2",
        "ciphertext": "CT",
        "nonce": "NONCE16CHARSXXX=",
        "signature": "SIG",
        "seqNo": 7,
        "digest": DIGEST,
    }
    assert "enc" not in sent


@responses.activate
def test_forward_targets_the_given_message_id(api):
    responses.add(responses.POST,
                  f"https://test.local/api/messages/{MID}/forward",
                  json={"data": {"id": "x"}}, status=201)

    api.forward(MID, "rid", "c", "n", "s", 1, DIGEST)

    assert responses.calls[0].request.url.endswith(f"/api/messages/{MID}/forward")


@responses.activate
def test_delete_targets_the_message_endpoint(api):
    responses.add(responses.DELETE,
                  f"https://test.local/api/messages/{MID}",
                  json={"data": {"message": "Message deleted"}}, status=200)

    api.delete(MID)

    assert responses.calls[0].request.url.endswith(f"/api/messages/{MID}")


@responses.activate
def test_delete_share_targets_the_shares_endpoint(api):
    # A forward must be deleted by its share id through the shares path — never
    # the message-delete path, which only knows the messages table.
    share_id = "share-abc"
    responses.add(responses.DELETE,
                  f"https://test.local/api/messages/shares/{share_id}",
                  json={"data": {"message": "Message deleted"}}, status=200)

    api.delete_share(share_id)

    assert responses.calls[0].request.url.endswith(
        f"/api/messages/shares/{share_id}")


@responses.activate
def test_send_body_has_no_enc(api):
    responses.add(responses.POST, "https://test.local/api/messages",
                  json={"data": {"messageId": "m1"}}, status=201)

    api.send("rid", "CT", "N", "SIG", 3, DIGEST)

    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"recipientId": "rid", "ciphertext": "CT", "nonce": "N",
                    "signature": "SIG", "seqNo": 3, "digest": DIGEST}
    assert "enc" not in sent
