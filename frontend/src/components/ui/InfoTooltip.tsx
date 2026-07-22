import React from 'react';
import Tooltip, { TooltipProps } from '@mui/material/Tooltip';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { styled } from '@mui/material/styles';

const StyledTooltip = styled(({ className, ...props }: TooltipProps) => (
  <Tooltip {...props} classes={{ popper: className }} />
))(({ theme }) => ({
  '& .MuiTooltip-tooltip': {
    backgroundColor: '#1E293B', // Slate 800
    color: '#F8FAFC', // Slate 50
    boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    fontSize: '0.8125rem',
    fontWeight: 500,
    lineHeight: 1.5,
    padding: '10px 14px',
    borderRadius: '8px',
    maxWidth: 280,
  },
  '& .MuiTooltip-arrow': {
    color: '#1E293B',
    '&::before': {
      border: '1px solid rgba(255, 255, 255, 0.1)',
    },
  },
}));

interface InfoTooltipProps {
  title: string;
  size?: number;
  ml?: number;
}

export const InfoTooltip: React.FC<InfoTooltipProps> = ({ title, size = 15, ml = 0.5 }) => {
  return (
    <StyledTooltip title={title} arrow placement="top" enterDelay={200} leaveDelay={200}>
      <InfoOutlinedIcon 
        sx={{ 
          fontSize: size, 
          ml: ml, 
          color: 'text.secondary', 
          cursor: 'help',
          opacity: 0.7,
          transition: 'all 0.2s',
          verticalAlign: 'middle',
          '&:hover': {
            opacity: 1,
            color: 'primary.main',
          }
        }} 
      />
    </StyledTooltip>
  );
};
