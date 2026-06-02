const { Router } = require('express');
const validate = require('../middleware/validate');

function messageRoutes(messageController, authMw) {
  const router = Router();

  // All message routes require authentication
  router.use(authMw);

  router.post('/', validate.sendMessage, messageController.send);
  router.get('/inbox', validate.pagination, messageController.inbox);
  router.get('/sent', validate.pagination, messageController.sent);
  router.get('/:id', messageController.getOne);
  router.get('/:id/chain', messageController.chainProof);
  router.post('/:id/forward', validate.forwardMessage, messageController.forward);
  router.get('/:id/shares', messageController.shares);
  router.post('/:id/revoke', validate.revokeAccess, messageController.revoke);
  // Delete a forward by its share id. Declared before DELETE /:id so the
  // two-segment path isn't shadowed, and so a share id can never be treated
  // as a message id (they live in different tables).
  router.delete('/shares/:shareId', messageController.removeShare);
  router.delete('/:id', messageController.remove);

  return router;
}

module.exports = messageRoutes;
