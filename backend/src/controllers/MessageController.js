class MessageController {
  constructor(messageService) {
    this._messageService = messageService;
  }

  send = async (req, res, next) => {
    try {
      // Destructure explicitly so a client can't override senderId via the body.
      // `digest` is the client-computed keccak256 of plaintext — the server
      // relays it to the blockchain listener without inspection.
      const { recipientId, ciphertext, nonce, signature, seqNo, digest } = req.body;
      const result = await this._messageService.sendMessage({
        senderId: req.user.id,
        recipientId,
        ciphertext,
        nonce,
        signature,
        seqNo,
        digest,
      });
      res.status(201).json({ data: result });
    } catch (err) {
      next(err);
    }
  };

  chainProof = async (req, res, next) => {
    try {
      const proof = await this._messageService.getChainProof(req.params.id, req.user.id);
      res.json({ data: proof });
    } catch (err) {
      next(err);
    }
  };

  inbox = async (req, res, next) => {
    try {
      const messages = await this._messageService.getInbox(req.user.id, {
        limit: req.query.limit || 50,
        offset: req.query.offset || 0,
      });
      res.json({ data: messages });
    } catch (err) {
      next(err);
    }
  };

  sent = async (req, res, next) => {
    try {
      const messages = await this._messageService.getSent(req.user.id, {
        limit: req.query.limit || 50,
        offset: req.query.offset || 0,
      });
      res.json({ data: messages });
    } catch (err) {
      next(err);
    }
  };

  getOne = async (req, res, next) => {
    try {
      const message = await this._messageService.getMessage(req.params.id, req.user.id);
      res.json({ data: message });
    } catch (err) {
      next(err);
    }
  };

  forward = async (req, res, next) => {
    try {
      const { recipientId, ciphertext, nonce, signature, seqNo, digest } = req.body;
      const result = await this._messageService.forwardMessage({
        messageId: req.params.id,
        forwarderId: req.user.id,
        recipientId,
        ciphertext,
        nonce,
        signature,
        seqNo,
        digest,
      });
      res.status(201).json({ data: result });
    } catch (err) {
      next(err);
    }
  };

  shares = async (req, res, next) => {
    try {
      const shares = await this._messageService.getShares(req.params.id, req.user.id);
      res.json({ data: shares });
    } catch (err) {
      next(err);
    }
  };

  revoke = async (req, res, next) => {
    try {
      await this._messageService.revokeAccess(req.params.id, req.user.id, req.body.userId);
      res.json({ data: { message: 'Access revoked' } });
    } catch (err) {
      next(err);
    }
  };

  remove = async (req, res, next) => {
    try {
      await this._messageService.deleteMessage(req.params.id, req.user.id);
      res.json({ data: { message: 'Message deleted' } });
    } catch (err) {
      next(err);
    }
  };

  removeShare = async (req, res, next) => {
    try {
      await this._messageService.deleteShare(req.params.shareId, req.user.id);
      res.json({ data: { message: 'Message deleted' } });
    } catch (err) {
      next(err);
    }
  };
}

module.exports = MessageController;
