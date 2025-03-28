import grpc
from concurrent import futures
import logging_pb2, logging_pb2_grpc

msg = {}

class LoggingService(logging_pb2_grpc.LoggingServiceServicer):
    def LogMessage(self, request, context):
        if request.id in msg:
            return logging_pb2.LogReply(status='Duplicate')
        msg[request.id] = request.txt
        print('Message:', request.txt)
        return logging_pb2.LogReply(status='Logged')

    def GetMessages(self, request, context):
        return logging_pb2.MessagesReply(messages=list(msg.values()))

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    logging_pb2_grpc.add_LoggingServiceServicer_to_server(LoggingService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
