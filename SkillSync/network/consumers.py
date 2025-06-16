import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import ChatMessage, TechBuddy
from django.db.models import Q

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.current_user = self.scope['user']
        
        if not self.current_user.is_authenticated:
            await self.close()
            return
        
        # Check if users are buddies
        is_buddy = await self.check_buddy_relationship()
        if not is_buddy:
            await self.close()
            return
        
        # Create unique room name for the two users
        user_ids = sorted([str(self.current_user.id), str(self.user_id)])
        self.room_name = f"chat_{'_'.join(user_ids)}"
        self.room_group_name = f'chat_{self.room_name}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']
        
        # Save message to database
        await self.save_message(message)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': self.current_user.username,
                'sender_id': self.current_user.id,
            }
        )
    
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'sender_id': event['sender_id'],
        }))
    
    @database_sync_to_async
    def check_buddy_relationship(self):
        return TechBuddy.objects.filter(
            Q(requester=self.current_user, receiver_id=self.user_id, status='accepted') |
            Q(receiver=self.current_user, requester_id=self.user_id, status='accepted')
        ).exists()
    
    @database_sync_to_async
    def save_message(self, message):
        receiver = User.objects.get(id=self.user_id)
        ChatMessage.objects.create(
            sender=self.current_user,
            receiver=receiver,
            message=message
        )