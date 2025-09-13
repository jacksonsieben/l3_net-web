from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from validation.models import Exam
import random


class Command(BaseCommand):
    help = 'Shuffle exams in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['all', 'by-version', 'image-paths'],
            default='all',
            help='Type of shuffling to perform (default: all)'
        )
        
        parser.add_argument(
            '--version',
            type=str,
            help='Specific version to shuffle (only used with --type=by-version)'
        )
        
        parser.add_argument(
            '--seed',
            type=int,
            help='Random seed for reproducible shuffling'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be shuffled without making changes'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )

    def handle(self, *args, **options):
        shuffle_type = options['type']
        version = options.get('version')
        seed = options.get('seed')
        dry_run = options['dry_run']
        force = options['force']

        # Get current exam count
        total_exams = Exam.objects.count()
        if total_exams == 0:
            self.stdout.write(
                self.style.WARNING('No exams found in the database.')
            )
            return

        self.stdout.write(f'Found {total_exams} exams in the database.')

        # Show what will be done
        if shuffle_type == 'all':
            action_desc = "Shuffle all exams by randomizing their IDs"
        elif shuffle_type == 'by-version':
            if version:
                version_count = Exam.objects.filter(version=version).count()
                action_desc = f"Shuffle {version_count} exams in version '{version}'"
            else:
                versions = list(Exam.objects.values_list('version', flat=True).distinct())
                action_desc = f"Shuffle exams within each version separately ({len(versions)} versions)"
        elif shuffle_type == 'image-paths':
            action_desc = "Shuffle image paths while keeping external IDs unchanged"

        self.stdout.write(f'\nAction: {action_desc}')
        
        if seed:
            self.stdout.write(f'Random seed: {seed}')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN: No changes will be made to the database.')
            )
            return

        # Confirmation prompt
        if not force:
            self.stdout.write(
                self.style.WARNING(
                    '\nWARNING: This will modify the database and cannot be easily undone!'
                )
            )
            confirm = input('Are you sure you want to proceed? (yes/no): ')
            if confirm.lower() not in ['yes', 'y']:
                self.stdout.write('Operation cancelled.')
                return

        # Perform the shuffling
        try:
            with transaction.atomic():
                if shuffle_type == 'all':
                    count = Exam.shuffle_all(seed=seed)
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully shuffled {count} exams.')
                    )
                
                elif shuffle_type == 'by-version':
                    result = Exam.shuffle_by_version(version=version, seed=seed)
                    total_shuffled = sum(result.values())
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully shuffled {total_shuffled} exams.')
                    )
                    
                    # Show breakdown by version
                    for ver, count in result.items():
                        if count > 0:
                            self.stdout.write(f'  Version "{ver}": {count} exams')
                        else:
                            self.stdout.write(f'  Version "{ver}": No shuffling needed (< 2 exams)')
                
                elif shuffle_type == 'image-paths':
                    count = Exam.shuffle_image_paths(seed=seed)
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully shuffled image paths for {count} exams.')
                    )

        except Exception as e:
            raise CommandError(f'Error during shuffling: {e}')

        self.stdout.write('\nShuffling completed successfully!')