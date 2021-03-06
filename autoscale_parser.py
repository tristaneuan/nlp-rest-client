from boto.ec2 import connect_to_region
from time import sleep
import traceback

# These values are set by autoscale_monitor.py
opt = {
        'region': None,
        'price': None,
        'ami': None,
        'count': None,
        'key': None,
        'sec': None,
        'type': None,
        'tag': None,
        'threshold': None,
        'max_size': None
      }

class EC2RegionConnection(object):
    """
    A connection to a specified EC2 region.
    """
    def __init__(self, region=opt['region']):
        """
        Open a boto.ec2.connection.EC2Connection object.

        :type region: string
        :param region: A string representing the EC2 region to connect to
        """
        self.conn = connect_to_region(region)

    def _request_instances(self, count):
        """
        Request spot instances.

        :type count: int
        :param count: The number of spot instances to request

        :rtype: boto.ec2.instance.Reservation
        :return: The Reservation object representing the spot instance request
        """
        if not isinstance(opt['sec'], list):
            opt['sec'] = opt['sec'].split(',')
        return self.conn.request_spot_instances(price=opt['price'],
                                                image_id=opt['ami'],
                                                count=count,
                                                key_name=opt['key'],
                                                security_groups=opt['sec'],
                                                instance_type=opt['type'])

    def _get_instance_ids(self, reservation):
        """
        Get instance IDs for a particular reservation.

        :type reservation: boto.ec2.instance.Reservation
        :param reservation: A Reservation object created by requesting spot
                            instances

        :rtype: list
        :return: A list containing strings representing the instance IDs of the
                 given Reservation
        """
        r_ids = [request.id for request in reservation]
        while True:
            sleep(5)
            requests = self.conn.get_all_spot_instance_requests(request_ids=r_ids)
            instance_ids = []
            for request in requests:
                instance_id = request.instance_id
                #print 'instance_id is %s' % instance_id
                if instance_id is None:
                    break
                #print 'appending %s' % instance_id
                instance_ids.append(instance_id)
            if len(instance_ids) < len(reservation):
                print 'waiting for %d instances to launch...' % len(reservation)
                continue
            break
        return instance_ids

    def _tag_instances(self, instance_ids):
        """
        Attach identifying tags to the specified instances.

        :type instance_ids: list
        :param instance_ids: A list of instance IDs to tag

        :rtype: boolean
        :return: A boolean indicating whether tagging was successful
        """
        tags = {'Name': opt['tag']}
        return self.conn.create_tags(instance_ids, tags)

    def add_instances(self, count):
        """
        Add a specified number of instances.

        :type count: int
        :param count: The number of instances to add

        :rtype: int
        :return: An integer indicating the number of active tagged instances
        """
        try:
            # Create spot instances
            reservation = self._request_instances(count)
            # Tag created spot instances
            instance_ids = self._get_instance_ids(reservation)
            self._tag_instances(instance_ids)
        except:
            traceback.print_exc()
        return len(self.get_tagged_instances())

    def terminate(self, instance_ids):
        """
        Terminate instances with the specified IDs.

        :type instance_ids: list
        :param instance_ids: A list of strings representing the instance IDs to
                             be terminated

        :rtype: boolean
        :return: A boolean indicating whether termination was successful
        """
        try:
            self.conn.terminate_instances(instance_ids)
        except:
            traceback.print_exc()
            return False
        return True

    def get_tagged_instances(self, tag=opt['tag']):
        """
        Get pending or running instances labeled with the tags specified in the
        options.

        :type tag: string
        :param tag: A string representing the tag name to operate over

        :rtype: list
        :return: A list of strings representing the IDs of the tagged instances
        """
        filters = {'tag:Name': tag}
        return [instance.id for reservation in
                self.conn.get_all_instances(filters=filters) for instance in
                reservation.instances if instance.state_code < 32]

if __name__ == '__main__':
    c = EC2RegionConnection()

    if opt['count']:
        difference = opt['count'] - len(c.get_tagged_instances())
        if difference > 0:
            c.add_instances(difference)

    # Get tagged instances
    tagged_instances = c.get_tagged_instances(opt['tag'])
    print tagged_instances # debug

